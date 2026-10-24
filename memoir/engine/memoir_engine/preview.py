"""On-demand preview thumbnails. Originals are never modified; previews are cached derivatives."""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import threading
import time

from . import config, db, exif, sources

_sem = threading.Semaphore(3)
_writes = 0
MAX_IMAGE_BYTES = 150 * 1024 * 1024
MAX_VIDEO_BYTES = 3 * 1024 * 1024 * 1024


def _placeholder(ext: str, label: str = "") -> bytes:
    ext = (ext or "file").upper()[:5]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 400"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#2a2f36"/><stop offset="1" stop-color="#14161a"/></linearGradient></defs>'
        '<rect width="300" height="400" fill="url(#g)"/><circle cx="150" cy="170" r="46" fill="none" stroke="#c8b07a" stroke-width="1.5"/>'
        f'<text x="150" y="178" text-anchor="middle" font-family="Georgia,serif" font-size="26" fill="#ece8df">{ext}</text>'
        f'<text x="150" y="250" text-anchor="middle" font-family="Georgia,serif" font-size="13" fill="#9b968c">{label or "No preview available"}</text></svg>'
    )
    return svg.encode()


def _from_bytes(data: bytes, w: int):
    from PIL import Image, ImageOps
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    im.thumbnail((w, int(w * 1.5)))
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=82)
    return out.getvalue()


def _tmp_copy(src, inner, ext, limit):
    path = sources.disk_path(src, inner)
    if path:
        return path, False
    info_size = db.one("SELECT size FROM media WHERE source_id=? AND inner=?", (src["id"], inner))["size"]
    if info_size and info_size > limit:
        return None, False
    tmp = os.path.join(str(config.tmp_dir()), f"pv{threading.get_ident()}_{int(time.time()*1000)}.{ext or 'bin'}")
    sources.copy_entry(src, inner, tmp)
    return tmp, True


def _video_frame(path: str, w: int):
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    for ss in ("0.5", "0"):
        try:
            r = subprocess.run([ff, "-loglevel", "error", "-ss", ss, "-i", path, "-frames:v", "1",
                                "-vf", f"scale='min({w},iw)':-2", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                               capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        if r.returncode == 0 and len(r.stdout) > 200:
            return r.stdout
    return None


def _generate(m: dict, src: dict, w: int):
    kind, ext = m["kind"], m["ext"]
    if kind == "image":
        if (m["size"] or 0) <= MAX_IMAGE_BYTES:
            try:
                return _from_bytes(sources.read_bytes(src, m["inner"]), w)
            except sources.SourceOffline:
                raise
            except Exception:
                pass
        tmp, is_tmp = _tmp_copy(src, m["inner"], ext, MAX_IMAGE_BYTES)
        if tmp:
            try:
                pv = exif.shared().preview_bytes(tmp)
                if pv:
                    return _from_bytes(pv, w)
            except Exception:
                pass
            finally:
                if is_tmp and os.path.exists(tmp):
                    os.remove(tmp)
        return None
    if kind == "raw":
        tmp, is_tmp = _tmp_copy(src, m["inner"], ext, MAX_IMAGE_BYTES)
        if not tmp:
            return None
        try:
            pv = exif.shared().preview_bytes(tmp)
            return _from_bytes(pv, w) if pv else None
        except Exception:
            return None
        finally:
            if is_tmp and os.path.exists(tmp):
                os.remove(tmp)
    if kind == "video":
        tmp, is_tmp = _tmp_copy(src, m["inner"], ext, MAX_VIDEO_BYTES)
        if not tmp:
            return None
        try:
            frame = _video_frame(tmp, w)
            return _from_bytes(frame, w) if frame else None
        except Exception:
            return None
        finally:
            if is_tmp and os.path.exists(tmp):
                os.remove(tmp)
    return None


def get_preview(media_id: int, w: int = 480):
    """Returns (bytes, content_type) for a thumbnail or a placeholder."""
    global _writes
    w = 1600 if w > 800 else 480
    config.ensure()
    cache = config.thumbs_dir() / f"{media_id}_{w}.jpg"
    if cache.exists():
        return cache.read_bytes(), "image/jpeg"
    m = db.one("SELECT * FROM media WHERE id=?", (media_id,))
    if not m:
        raise KeyError("media not found")
    src = db.one("SELECT * FROM sources WHERE id=?", (m["source_id"],))
    with _sem:
        if cache.exists():
            return cache.read_bytes(), "image/jpeg"
        try:
            data = _generate(m, src, w)
        except sources.SourceOffline:
            return _placeholder(m["ext"], "Drive offline"), "image/svg+xml"
    if not data:
        return _placeholder(m["ext"]), "image/svg+xml"
    cache.write_bytes(data)
    _writes += 1
    if _writes % 200 == 0:
        trim_cache()
    return data, "image/jpeg"


def cache_size() -> int:
    d = config.thumbs_dir()
    return sum(f.stat().st_size for f in d.glob("*.jpg")) if d.exists() else 0


def trim_cache():
    limit = config.thumb_cache_limit()
    files = sorted(config.thumbs_dir().glob("*.jpg"), key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    for f in files:
        if total <= limit * 0.8:
            break
        total -= f.stat().st_size
        try:
            f.unlink()
        except OSError:
            pass


def clear_cache() -> int:
    n = 0
    for f in config.thumbs_dir().glob("*.jpg"):
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n
