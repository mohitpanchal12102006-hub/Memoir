"""Lossless streaming export: copy, embed capture date, set file times, organize."""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import time
import zipfile
from datetime import datetime

from . import config, db, dates, exif, fsinfo, sources
from .jobs import Job
from .sources import SourceOffline

MEDIA = "('image','raw','video')"
NOT_WRITABLE = {"mkv", "webm", "avi", "mts", "m2ts", "mpg", "mpeg", "bmp", "mp"}
BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_OFFSET = re.compile(r"^[+-]\d{2}:\d{2}$")
COLS = "m.id, m.name, m.folder, m.kind, m.ext, m.size, m.status, m.ts, m.resolved, m.sha256, m.live_pair, m.source_id, m.inner"


class ExportError(Exception):
    pass


def normalize(opts: dict) -> dict:
    o = dict(opts or {})
    dest = o.get("destination") or {}
    dtype = dest.get("type", "folder")
    if dtype not in ("folder", "zip"):
        raise ExportError("Destination type must be 'folder' or 'zip'.")
    path = os.path.abspath(os.path.expanduser(str(dest.get("path", "")).strip().strip('"')))
    if not dest.get("path"):
        raise ExportError("Choose a destination.")
    struct = o.get("structure", "year-month")
    if struct not in ("flat", "year", "year-month"):
        raise ExportError("Unknown folder structure.")
    tz = o.get("sidecar_tz") or None
    if tz and not _OFFSET.match(tz):
        raise ExportError("Timezone must look like +05:30 or -08:00.")
    return {
        "destination": {"type": dtype, "path": path},
        "structure": struct, "prefix": bool(o.get("prefix", True)),
        "include_review": bool(o.get("include_review", False)),
        "unresolved": o.get("unresolved", "skip") if o.get("unresolved") in ("skip", "folder") else "skip",
        "sidecar_tz": tz, "date_from": o.get("date_from") or None, "date_to": o.get("date_to") or None,
        "folders": o.get("folders") or None,
    }


def _where(o: dict, a="m"):
    clauses = [f"{a}.kind IN {MEDIA}", f"{a}.hidden=0", f"{a}.excluded=0"]
    args = []
    if o["include_review"]:
        pass
    else:
        clauses.append(f"({a}.status IN ('ok','fixed') OR {a}.ts IS NULL)")
    if o["unresolved"] == "skip":
        clauses.append(f"{a}.ts IS NOT NULL")
    if o["date_from"]:
        clauses.append(f"{a}.ts >= ?")
        args.append(dates.naive_epoch(o["date_from"] + "T00:00:00"))
    if o["date_to"]:
        clauses.append(f"{a}.ts < ?")
        args.append(dates.naive_epoch(o["date_to"] + "T00:00:00") + 86400)
    if o["folders"]:
        clauses.append(f"{a}.folder IN ({','.join('?' * len(o['folders']))})")
        args += list(o["folders"])
    return " AND ".join(clauses), args


def preflight(opts: dict) -> dict:
    o = normalize(opts)
    errors, warnings = [], []
    w, a = _where(o)
    main = db.one(f"SELECT COUNT(*) c, COALESCE(SUM(size),0) s, MAX(size) mx FROM media m WHERE {w}", a)
    wp, ap = _where(o, "p")
    part = db.one(f"SELECT COUNT(*) c, COALESCE(SUM(v.size),0) s FROM media v JOIN media p ON p.id=v.live_pair "
                  f"WHERE v.hidden=1 AND v.excluded=0 AND {wp}", ap)
    files, size = main["c"] + part["c"], main["s"] + part["s"]
    skipped = {
        "needs_review": db.one(f"SELECT COUNT(*) c FROM media WHERE kind IN {MEDIA} AND hidden=0 AND excluded=0 AND status='review' AND ts IS NOT NULL")["c"] if not o["include_review"] else 0,
        "no_date": db.one(f"SELECT COUNT(*) c FROM media WHERE kind IN {MEDIA} AND hidden=0 AND excluded=0 AND ts IS NULL")["c"] if o["unresolved"] == "skip" else 0,
        "removed_duplicates": db.one(f"SELECT COUNT(*) c FROM media WHERE kind IN {MEDIA} AND hidden=0 AND excluded=1")["c"],
    }
    dest = o["destination"]
    base = dest["path"] if dest["type"] == "folder" else os.path.dirname(dest["path"])
    srcs = db.q("SELECT path, kind FROM sources")
    for s in srcs:
        if s["kind"] == "folder":
            sp = os.path.abspath(s["path"])
            tgt = os.path.abspath(dest["path"])
            if tgt == sp or tgt.startswith(sp + os.sep):
                errors.append("The destination is inside a source folder. Choose a different location.")
                break
    parent = base
    while parent and not os.path.exists(parent):
        nxt = os.path.dirname(parent)
        if nxt == parent:
            break
        parent = nxt
    if not os.path.isdir(parent) or not os.access(parent, os.W_OK):
        errors.append("The destination is not writable or its drive is not connected.")
    if dest["type"] == "zip":
        if not dest["path"].lower().endswith(".zip"):
            errors.append("A ZIP destination must end with .zip.")
        if os.path.exists(dest["path"]):
            errors.append("That ZIP file already exists. Choose a new name.")
    free = fsinfo.free_bytes(base) if os.path.isdir(parent) else 0
    need = int(size * 1.02) + (size if dest["type"] == "zip" else 0) * 0
    if free < need:
        errors.append("Not enough free space on the destination drive.")
    fs = fsinfo.fs_type(base)
    if fsinfo.is_fat(fs):
        warnings.append("The destination is formatted as FAT32: it stores file times with only 2-second precision and cannot hold files over 4 GB.")
        if (main["mx"] or 0) >= 4 * 1024 ** 3:
            errors.append("Some files are larger than 4 GB and cannot be stored on a FAT32 drive.")
    same = any(fsinfo.same_device(s["path"], base) for s in srcs if os.path.exists(s["path"]))
    if same:
        warnings.append("Source and destination are on the same drive. Copying will be slower.")
    if not exif.available():
        errors.append("exiftool was not found, but it is required to embed capture dates. Install it from https://exiftool.org.")
    unsup = db.one(f"SELECT COUNT(*) c FROM media m WHERE {w} AND m.ext IN ({','.join('?' * len(NOT_WRITABLE))})",
                   a + sorted(NOT_WRITABLE))["c"]
    if unsup:
        warnings.append(f"{unsup} files are in formats where dates cannot be embedded (such as MKV or AVI). "
                        "They are still copied with file timestamps and the date prefix.")
    if files == 0:
        errors.append("Nothing to export with these options.")
    return {"files": files, "bytes": size, "free": free, "filesystem": fs, "same_drive": same, "skipped": skipped,
            "warnings": warnings, "errors": errors, "ok": not errors, "normalized": o}


# ------------------------------------------------------------------ run
def _safe(name: str) -> str:
    return BAD.sub("_", name).strip(" .") or "file"


def export_time(row, o):
    r = db.jl(row["resolved"])
    local, tz = r["value"], r.get("tz")
    if tz == "Z" and o.get("sidecar_tz"):
        local = (datetime.fromisoformat(local) + dates.tz_delta(o["sidecar_tz"])).isoformat()
        tz = o["sidecar_tz"]
    return local, tz


def _rel_path(row, o, local):
    name = _safe(row["name"])
    if local is None:
        return ["_Unsorted"], name
    dt = datetime.fromisoformat(local)
    if o["prefix"]:
        name = f"{dt:%Y-%m-%d_%H-%M-%S}_{name}"
    parts = []
    if o["structure"] in ("year", "year-month"):
        parts.append(f"{dt:%Y}")
    if o["structure"] == "year-month":
        parts.append(f"{dt:%m}")
    return parts, name


def _unique(parts, name, used, root):
    base, ext = os.path.splitext(name)
    n, cand = 0, name
    while True:
        key = "/".join(parts + [cand]).lower()
        full = os.path.join(root, *parts, cand) if root else None
        if key not in used and not (full and os.path.exists(full)):
            used.add(key)
            return cand
        n += 1
        cand = f"{base}_{n}{ext}"


def start(job: Job, opts: dict, resume_id: int | None = None):
    job.stage = "export"
    if resume_id:
        ex = db.one("SELECT * FROM exports WHERE id=?", (resume_id,))
        if not ex:
            raise ExportError("Export not found.")
        o = json.loads(ex["options"])
        eid = resume_id
        db.run("UPDATE exports SET state='running' WHERE id=?", (eid,))
    else:
        pf = preflight(opts)
        if pf["errors"]:
            raise ExportError(" ".join(pf["errors"]))
        o = pf["normalized"]
        cur = db.run("INSERT INTO exports(created,dest,options,state) VALUES(?,?,?,'running')",
                     (time.time(), o["destination"]["path"], json.dumps(o), ))
        eid = cur.lastrowid
        w, a = _where(o)
        ids = [r[0] for r in db.conn().execute(f"SELECT m.id FROM media m WHERE {w} ORDER BY m.ts, m.id", a).fetchall()]
        db.many("INSERT OR IGNORE INTO export_items(export_id, media_id, state) VALUES(?,?,'pending')", [(eid, i) for i in ids])
        db.run("INSERT OR IGNORE INTO export_items(export_id, media_id, state) "
               "SELECT ?, v.id, 'pending' FROM media v JOIN export_items e ON e.media_id=v.live_pair AND e.export_id=? "
               "WHERE v.hidden=1 AND v.excluded=0", (eid, eid))
    job.params["export_id"] = eid
    tot = db.one("SELECT COUNT(*) c, COALESCE(SUM(m.size),0) s FROM export_items e JOIN media m ON m.id=e.media_id WHERE e.export_id=? AND e.state='pending'", (eid,))
    job.total, job.done = tot["c"], 0
    job.bytes_total, job.bytes_done = tot["s"], 0
    dest = o["destination"]
    is_zip = dest["type"] == "zip"
    root = None if is_zip else dest["path"]
    zf, partial = None, None
    if is_zip:
        partial = dest["path"] + ".partial"
        zf = zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED, allowZip64=True)
    else:
        os.makedirs(root, exist_ok=True)
    used = {r["dest_path"].lower() for r in db.q("SELECT dest_path FROM export_items WHERE export_id=? AND dest_path IS NOT NULL", (eid,))}
    src_cache = {}
    counts = {"done": 0, "failed": 0, "embed_failed": 0}
    try:
        while True:
            rows = db.q(f"SELECT {COLS}, e.dest_path AS planned FROM export_items e JOIN media m ON m.id=e.media_id "
                        "WHERE e.export_id=? AND e.state='pending' ORDER BY m.id LIMIT 300", (eid,))
            if not rows:
                break
            for row in rows:
                while True:
                    job.checkpoint()
                    job.message = f"Exporting {row['name']}"
                    try:
                        state, note, rel = _item(job, row, o, root, zf, used, src_cache)
                        break
                    except SourceOffline as e:
                        sources.drop_zip(src_cache.get(row["source_id"], {}).get("path", ""))
                        job.pause(f"A source drive went offline ({e}). Reconnect it and press Resume.")
                        job.checkpoint()
                        src_cache.pop(row["source_id"], None)
                    except OSError as e:
                        if root and not os.path.isdir(root):
                            job.pause("The destination drive went offline. Reconnect it and press Resume.")
                            job.checkpoint()
                            continue
                        state, note, rel = "failed", {"error": f"{type(e).__name__}: {e}"}, None
                        break
                    except Exception as e:  # noqa: BLE001
                        state, note, rel = "failed", {"error": f"{type(e).__name__}: {e}"}, None
                        break
                counts["done" if state == "done" else "failed"] += 1
                if state == "done" and str(note.get("embed", "")).startswith(("skipped", "failed")):
                    counts["embed_failed"] += 1
                db.run("UPDATE export_items SET state=?, dest_path=?, note=? WHERE export_id=? AND media_id=?",
                       (state, rel, json.dumps(note), eid, row["id"]))
                job.done += 1
    except BaseException:
        if zf:
            zf.close()
            try:
                os.remove(partial)
            except OSError:
                pass
        db.run("UPDATE exports SET state='interrupted' WHERE id=?", (eid,))
        raise
    if zf:
        zf.close()
        os.replace(partial, dest["path"])
    report = config.reports_dir() / f"export-{eid}.csv"
    with open(report, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["state", "name", "source_inner", "destination", "note"])
        for r in db.q("SELECT e.state, m.name, m.inner, e.dest_path, e.note FROM export_items e JOIN media m ON m.id=e.media_id WHERE e.export_id=?", (eid,)):
            w.writerow([r["state"], r["name"], r["inner"], r["dest_path"], r["note"]])
    db.run("UPDATE exports SET state='done' WHERE id=?", (eid,))
    job.result.update(counts | {"export_id": eid, "report": str(report), "bytes": job.bytes_done})
    job.message = "Export complete"


def _item(job, row, o, root, zf, used, src_cache):
    src = src_cache.get(row["source_id"]) or src_cache.setdefault(row["source_id"], db.one("SELECT * FROM sources WHERE id=?", (row["source_id"],)))
    local, tz = (export_time(row, o) if row["ts"] is not None else (None, None))
    if row.get("planned"):  # reserved by an earlier (interrupted) run: reuse the same path
        pieces = row["planned"].split("/")
        parts, name = pieces[:-1], pieces[-1]
    else:
        parts, name = _rel_path(row, o, local)
        name = _unique(parts, name, used, root)
        db.run("UPDATE export_items SET dest_path=? WHERE export_id=? AND media_id=?",
               ("/".join(parts + [name]), job.params["export_id"], row["id"]))
    rel = "/".join(parts + [name])
    if root:
        final = os.path.join(root, *parts, name)
        os.makedirs(os.path.dirname(final), exist_ok=True)
        tmp = os.path.join(os.path.dirname(final), f".memoir-{row['id']}.tmp.{row['ext']}")
    else:
        os.makedirs(str(config.tmp_dir()), exist_ok=True)
        tmp = os.path.join(str(config.tmp_dir()), f"x{row['id']}.tmp.{row['ext']}")
    note = {}
    try:
        sha, _ = sources.copy_entry(src, row["inner"], tmp, job.add_bytes)
        if row["sha256"] and sha != row["sha256"]:
            raise ValueError("checksum mismatch between the source and the copy")
        if local is not None:
            ok, msg = exif.shared().write_dates(tmp, "video" if row["kind"] == "video" else "image", local, tz)
            note["embed"] = "written" if ok else "skipped: " + (msg[:160] or "format not writable")
            note["times"] = fsinfo.set_file_times(tmp, local)
        else:
            note["embed"] = "none (no date)"
        if root:
            os.replace(tmp, final)
        else:
            dt = datetime.fromisoformat(local) if local else datetime(1980, 1, 1)
            dt = dt if dt.year >= 1980 else datetime(1980, 1, 1)
            zi = zipfile.ZipInfo(rel, (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second))
            zi.compress_type = zipfile.ZIP_STORED
            with open(tmp, "rb") as fh, zf.open(zi, "w", force_zip64=True) as out:
                shutil.copyfileobj(fh, out, 1 << 20)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return "done", note, rel
