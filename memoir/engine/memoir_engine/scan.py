"""Indexing, sidecar matching and the deep scan (hashes + metadata + date resolution)."""
from __future__ import annotations

import errno
import json
import os
import re
import zipfile
import zlib

from . import config, db, dates, exif, formats, fsinfo, sidecars, sources
from .jobs import Job
from .sources import SourceOffline

PART_RE = re.compile(r"^takeout-(\d{8}T\d{6}Z)(?:-\d+)?-(\d{3,})\.zip$", re.I)
SKIP_JSON = {"metadata.json", "print-subscriptions.json", "shared_album_comments.json",
             "user-generated-memory-titles.json"}
MEDIA_KINDS = ("image", "raw", "video")


def display_folder(inner: str) -> str:
    d = inner.rsplit("/", 1)[0] if "/" in inner else ""
    for p in ("Takeout/Google Photos", "Takeout/Google Fotos", "Takeout"):
        if d == p:
            return "(root)"
        if d.startswith(p + "/"):
            d = d[len(p) + 1:]
            break
    return d or "(root)"


# ---------------------------------------------------------------- sources
def add_sources(paths):
    added, errors = [], []
    for raw in paths:
        p = os.path.abspath(os.path.expanduser(str(raw).strip().strip('"')))
        if not os.path.exists(p):
            errors.append({"path": raw, "error": "Path not found. Is the drive connected?"})
            continue
        targets = [p]
        if os.path.isdir(p):
            zips = sorted(os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(".zip")
                          and os.path.isfile(os.path.join(p, f)))
            if zips:
                targets = zips
        for t in targets:
            if os.path.isdir(t):
                kind, size = "folder", 0
            elif zipfile.is_zipfile(t):
                kind, size = "zip", os.path.getsize(t)
            else:
                errors.append({"path": t, "error": "Not a ZIP archive or a folder."})
                continue
            m = PART_RE.match(os.path.basename(t)) if kind == "zip" else None
            existing = db.one("SELECT * FROM sources WHERE path=?", (t,))
            if existing:
                added.append(existing)
                continue
            cur = db.run(
                "INSERT INTO sources(kind,path,size,mtime,location,part_group,part_no,state) VALUES(?,?,?,?,?,?,?,?)",
                (kind, t, size, os.path.getmtime(t), fsinfo.location_of(t),
                 m.group(1) if m else None, int(m.group(2)) if m else None, "queued"))
            added.append(db.one("SELECT * FROM sources WHERE id=?", (cur.lastrowid,)))
    return {"added": added, "errors": errors}


def list_sources():
    rows = db.q("SELECT s.* FROM sources s ORDER BY COALESCE(part_group,''), COALESCE(part_no,0), id")
    counts = {r["source_id"]: r for r in db.q(
        "SELECT source_id, COUNT(*) AS mc, SUM(scanned) AS sc FROM media WHERE kind IN ('image','raw','video') GROUP BY source_id")}
    for r in rows:
        c = counts.get(r["id"])
        r["media_count"], r["scanned_count"] = (c["mc"], c["sc"] or 0) if c else (0, 0)
        r["online"] = os.path.exists(r["path"])
        if not r["online"] and r["state"] not in ("error",):
            r["state"] = "offline"
    return rows


def takeout_sets():
    groups = {}
    for s in list_sources():
        if s["part_group"]:
            groups.setdefault(s["part_group"], []).append(s)
    out = []
    for g, parts in groups.items():
        nums = {p["part_no"] for p in parts}
        top = max(nums)
        out.append({
            "group": g, "parts": parts, "count": len(parts), "size": sum(p["size"] for p in parts),
            "highest_part": top, "missing": sorted(set(range(1, top + 1)) - nums),
        })
    return out


def relink(source_id: int, new_path: str):
    s = db.one("SELECT * FROM sources WHERE id=?", (source_id,))
    if not s:
        raise KeyError("source not found")
    p = os.path.abspath(os.path.expanduser(new_path.strip().strip('"')))
    if s["kind"] == "zip":
        if not os.path.isfile(p) or os.path.getsize(p) != s["size"]:
            raise ValueError("That file does not exist or its size differs from the original part.")
    elif not os.path.isdir(p):
        raise ValueError("That folder does not exist.")
    sources.drop_zip(s["path"])
    db.run("UPDATE sources SET path=?, location=?, state=CASE WHEN state='offline' THEN 'indexed' ELSE state END WHERE id=?",
           (p, fsinfo.location_of(p), source_id))
    return db.one("SELECT * FROM sources WHERE id=?", (source_id,))


# ---------------------------------------------------------------- index
def _entries(src):
    if src["kind"] == "zip":
        zf = sources.get_zip(src["path"])
        for i in zf.infolist():
            if not i.is_dir():
                yield i.filename, i.file_size
    else:
        root = src["path"]
        for d, _dirs, files in os.walk(root):
            for f in files:
                full = os.path.join(d, f)
                inner = os.path.relpath(full, root).replace(os.sep, "/")
                try:
                    yield inner, os.path.getsize(full)
                except OSError:
                    continue


def index_source(job: Job, src: dict):
    batch, count = [], 0
    try:
        for inner, size in _entries(src):
            job.checkpoint()
            if formats.is_ignored(inner):
                continue
            name = inner.rsplit("/", 1)[-1]
            kind = formats.kind_of(name)
            if kind == "other" or (kind == "sidecar" and name.lower() in SKIP_JSON):
                continue
            folder = display_folder(inner)
            batch.append((src["id"], inner, name, folder, folder, formats.ext_of(name), kind, size,
                          "sidecar" if kind == "sidecar" else "pending"))
            count += 1
            if len(batch) >= 2000:
                _flush(batch)
                batch = []
        _flush(batch)
    except SourceOffline as e:
        db.run("UPDATE sources SET state='offline', error=? WHERE id=?", (str(e), src["id"]))
        return False
    except zipfile.BadZipFile as e:
        db.run("UPDATE sources SET state='error', error=? WHERE id=?", (f"Damaged ZIP: {e}", src["id"]))
        return False
    db.run("UPDATE sources SET state='indexed', entries=?, error=NULL WHERE id=?", (count, src["id"]))
    return True


def _flush(batch):
    if batch:
        db.many("INSERT OR IGNORE INTO media(source_id,inner,name,folder,dirkey,ext,kind,size,status) VALUES(?,?,?,?,?,?,?,?,?)", batch)


def index_all(job: Job):
    job.stage = "index"
    todo = db.q("SELECT * FROM sources WHERE state IN ('queued','offline') ORDER BY id")
    job.total = len(todo)
    job.done = 0
    for src in todo:
        job.checkpoint()
        job.message = f"Reading ZIP directory: {os.path.basename(src['path'])}"
        index_source(job, src)
        job.done += 1


# ---------------------------------------------------------------- match
def match_all(job: Job):
    job.stage = "match"
    job.message = "Matching sidecars and Live Photos"
    media = db.q("SELECT id,name,dirkey FROM media WHERE kind IN ('image','raw','video') AND sidecar_id IS NULL")
    scs = db.q("SELECT id,name,dirkey FROM media WHERE kind='sidecar'")
    mapping, orphans = sidecars.match(media, scs)
    db.many("UPDATE media SET sidecar_id=? WHERE id=?", [(sid, mid) for mid, sid in mapping.items()])
    used = {r["sidecar_id"] for r in db.q("SELECT DISTINCT sidecar_id FROM media WHERE sidecar_id IS NOT NULL")}
    db.many("UPDATE media SET status=? WHERE id=?",
            [("matched" if s["id"] in used else "orphan", s["id"]) for s in scs])
    # Live Photos: still + short video sharing a base name in the same folder
    stills, vids = {}, {}
    for r in db.q("SELECT id,name,dirkey,ext,kind,size FROM media WHERE kind IN ('image','video') AND live_pair IS NULL"):
        stem = os.path.splitext(r["name"])[0].lower()
        key = (r["dirkey"], stem)
        if r["kind"] == "image" and r["ext"] in formats.STILL_FOR_LIVE:
            stills.setdefault(key, r)
        elif r["kind"] == "video" and r["ext"] in formats.VIDEO_FOR_LIVE:
            vids.setdefault(key, r)
    pairs = []
    for key, v in vids.items():
        s = stills.get(key)
        if s and (s["ext"] in ("heic", "heif") or v["size"] <= 20 * 1024 * 1024):
            pairs.append((s["id"], s["id"], 0))
            pairs.append((s["id"], v["id"], 1))
    db.many("UPDATE media SET live_pair=?, hidden=? WHERE id=?", [(p, h, i) for p, i, h in pairs])
    job.result["orphan_sidecars"] = len(orphans)
    job.result["live_photos"] = len(pairs) // 2


# ---------------------------------------------------------------- deep scan
def _sidecar_candidate(row, src_cache):
    sc = db.one("SELECT source_id, inner FROM media WHERE id=?", (row["sidecar_id"],))
    if not sc:
        return None
    ssrc = src_cache.get(sc["source_id"])
    if ssrc is None:
        ssrc = src_cache[sc["source_id"]] = db.one("SELECT * FROM sources WHERE id=?", (sc["source_id"],))
    try:
        data = json.loads(sources.read_bytes(ssrc, sc["inner"], 2_000_000).decode("utf-8", "replace"))
    except (ValueError, zipfile.BadZipFile, zlib.error):
        return None
    ts = (data.get("photoTakenTime") or {}).get("timestamp")
    return dates.sidecar_candidate(ts) if ts is not None else None


def _process(src, row, job, src_cache):
    tmp, sha, info, err = None, None, {"cands": [], "width": None, "height": None, "error": None}, None
    try:
        if src["kind"] == "folder":
            path = sources.disk_path(src, row["inner"])
            sha, _ = sources.hash_entry(src, row["inner"], job.add_bytes)
        else:
            tmp = os.path.join(str(config.tmp_dir()), f"m{row['id']}.{row['ext'] or 'bin'}")
            sha, _ = sources.copy_entry(src, row["inner"], tmp, job.add_bytes)
            path = tmp
        info = exif.shared().read(path)
    except SourceOffline:
        raise
    except (zipfile.BadZipFile, zlib.error, EOFError) as e:
        err = f"damaged data: {e}"
    except OSError as e:
        if e.errno == errno.ENOSPC:
            raise
        err = f"read error: {e}"
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    cands = list(info["cands"])
    if row["sidecar_id"]:
        c = _sidecar_candidate(row, src_cache)
        if c:
            cands.append(c)
    fc = dates.filename_candidate(row["name"])
    if fc:
        cands.append(fc)
    error = err or info.get("error")
    resolved, status, reasons, ts = dates.resolve(cands, db.jl(row["manual"]), has_error=bool(error))
    db.conn().execute(
        "UPDATE media SET sha256=?, width=?, height=?, cands=?, resolved=?, ts=?, status=?, reasons=?, scanned=1, error=?, has_exif=? WHERE id=?",
        (sha, info.get("width"), info.get("height"), json.dumps(cands), json.dumps(resolved) if resolved else None,
         ts, status, json.dumps(reasons), error, 1 if any(c["source"] == "exif" and not c.get("bad") for c in cands) else 0, row["id"]))


def propagate_live():
    rows = db.q("SELECT v.id AS vid, s.resolved, s.ts, s.status, s.reasons FROM media v JOIN media s ON s.id=v.live_pair "
                "WHERE v.hidden=1 AND s.scanned=1")
    db.many("UPDATE media SET resolved=?, ts=?, status=?, reasons=?, scanned=1 WHERE id=?",
            [(r["resolved"], r["ts"], r["status"], r["reasons"], r["vid"]) for r in rows])


def deep_scan(job: Job):
    if not exif.available():
        raise RuntimeError("exiftool was not found. Install it from https://exiftool.org and add it to PATH.")
    job.stage = "scan"
    tot = db.one("SELECT COUNT(*) c, COALESCE(SUM(size),0) s FROM media WHERE kind IN ('image','raw','video') AND scanned=0 AND hidden=0")
    job.total, job.done = tot["c"], 0
    job.bytes_total, job.bytes_done = tot["s"], 0
    src_cache, pending = {}, 0
    for src in db.q("SELECT * FROM sources WHERE state!='error' ORDER BY COALESCE(part_group,''), COALESCE(part_no,0), id"):
        rows = db.q("SELECT id,inner,name,ext,size,sidecar_id,manual FROM media WHERE source_id=? AND hidden=0 "
                    "AND kind IN ('image','raw','video') AND scanned=0 ORDER BY id", (src["id"],))
        for row in rows:
            while True:
                job.checkpoint()
                try:
                    job.message = f"Scanning {src['path'].rsplit(os.sep, 1)[-1]}"
                    _process(src, row, job, src_cache)
                    break
                except SourceOffline as e:
                    db.conn().commit()
                    db.run("UPDATE sources SET state='offline', error=? WHERE id=?", (str(e), src["id"]))
                    sources.drop_zip(src["path"])
                    job.pause(f"Drive offline: {src['path']}. Reconnect it and press Resume.")
                    job.checkpoint()
                    src = db.one("SELECT * FROM sources WHERE id=?", (src["id"],))
                    db.run("UPDATE sources SET state='indexed', error=NULL WHERE id=?", (src["id"],))
            job.done += 1
            pending += 1
            if pending >= 25:
                db.conn().commit()
                pending = 0
    db.conn().commit()
    propagate_live()
    from . import duplicates
    duplicates.refresh_index(force=True)
    job.result.update(summary())


def run_pipeline(job: Job):
    index_all(job)
    match_all(job)
    deep_scan(job)
    job.stage = "done"
    job.message = "Scan complete"


# ---------------------------------------------------------------- manual fixes
def recompute(ids):
    for chunk in [ids[i:i + 500] for i in range(0, len(ids), 500)]:
        ph = ",".join("?" * len(chunk))
        rows = db.q(f"SELECT id,cands,manual,error FROM media WHERE id IN ({ph})", chunk)
        upd = []
        for r in rows:
            resolved, status, reasons, ts = dates.resolve(db.jl(r["cands"], []), db.jl(r["manual"]), has_error=bool(r["error"]))
            upd.append((json.dumps(resolved) if resolved else None, ts, status, json.dumps(reasons), r["id"]))
        db.many("UPDATE media SET resolved=?, ts=?, status=?, reasons=? WHERE id=?", upd)
    propagate_live()


def summary():
    r = db.one("SELECT COUNT(*) total,"
               " SUM(kind='image') images, SUM(kind='raw') raws, SUM(kind='video') videos,"
               " SUM(status='review') review, SUM(status IN ('ok','fixed')) ok"
               " FROM media WHERE kind IN ('image','raw','video') AND hidden=0")
    o = db.one("SELECT COUNT(*) c FROM media WHERE kind='sidecar' AND status='orphan'")
    return {k: (v or 0) for k, v in r.items()} | {"orphan_sidecars": o["c"]}
