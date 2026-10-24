"""Reading entries from ZIP archives and folders, in place and read-only."""
from __future__ import annotations

import hashlib
import os
import threading
import zipfile

CHUNK = 1 << 20


class SourceOffline(Exception):
    """The drive or file is not reachable right now."""


_zips: dict = {}
_lock = threading.Lock()


def get_zip(path: str) -> zipfile.ZipFile:
    with _lock:
        zf = _zips.get(path)
        if zf is None:
            try:
                zf = zipfile.ZipFile(path)
            except zipfile.BadZipFile:
                raise
            except OSError as e:
                raise SourceOffline(str(e))
            _zips[path] = zf
        return zf


def drop_zip(path: str) -> None:
    with _lock:
        zf = _zips.pop(path, None)
    if zf:
        try:
            zf.close()
        except Exception:
            pass


def close_all() -> None:
    with _lock:
        items = list(_zips.values())
        _zips.clear()
    for z in items:
        try:
            z.close()
        except Exception:
            pass


def disk_path(src: dict, inner: str):
    """Real path for folder sources, None for ZIP sources."""
    if src["kind"] == "folder":
        return os.path.join(src["path"], *inner.split("/"))
    return None


def open_entry(src: dict, inner: str):
    if src["kind"] == "folder":
        try:
            return open(disk_path(src, inner), "rb")
        except FileNotFoundError:
            if not os.path.exists(src["path"]):
                raise SourceOffline(src["path"])
            raise
        except OSError as e:
            raise SourceOffline(str(e))
    zf = get_zip(src["path"])
    try:
        return zf.open(inner)
    except KeyError:
        raise FileNotFoundError(inner)
    except (OSError, ValueError) as e:
        drop_zip(src["path"])
        raise SourceOffline(str(e))


def read_bytes(src: dict, inner: str, limit: int | None = None) -> bytes:
    with open_entry(src, inner) as f:
        return f.read(limit) if limit else f.read()


def copy_entry(src: dict, inner: str, dest_path: str, progress=None):
    """Stream an entry to dest_path. Returns (sha256 hex, size). ZIP CRC is checked while reading."""
    h = hashlib.sha256()
    size = 0
    try:
        with open_entry(src, inner) as f, open(dest_path, "wb") as out:
            while True:
                b = f.read(CHUNK)
                if not b:
                    break
                h.update(b)
                out.write(b)
                size += len(b)
                if progress:
                    progress(len(b))
    except OSError as e:
        if isinstance(e, SourceOffline):
            raise
        raise
    return h.hexdigest(), size


def hash_entry(src: dict, inner: str, progress=None):
    h = hashlib.sha256()
    size = 0
    with open_entry(src, inner) as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
            size += len(b)
            if progress:
                progress(len(b))
    return h.hexdigest(), size
