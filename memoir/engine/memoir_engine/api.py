"""HTTP API (FastAPI). Runs locally; serves the web UI from ./static."""
from __future__ import annotations

import json
import os
import pathlib
import platform
import shutil
import string
from datetime import datetime, timedelta

from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from urllib.parse import urlparse

from . import __version__, config, db, dates, duplicates, exif, export, jobs, preview, scan, sources

@asynccontextmanager
async def lifespan(_app):
    config.ensure()
    db.conn()
    yield
    exif.shutdown()
    sources.close_all()


app = FastAPI(title="Memoir", version=__version__, lifespan=lifespan)

_LOCAL = {"127.0.0.1", "localhost", "::1"}


def _allowed_hosts():
    return _LOCAL | {h.strip() for h in os.environ.get("MEMOIR_ALLOWED_HOSTS", "").split(",") if h.strip()}


@app.middleware("http")
async def local_only_guard(request, call_next):
    """Only the Memoir page on this computer may use the API (blocks other websites and DNS rebinding)."""
    host = urlparse("//" + request.headers.get("host", "")).hostname
    origin = request.headers.get("origin")
    bad = host not in _allowed_hosts()
    if not bad and origin and origin != "null":
        bad = urlparse(origin).hostname not in _allowed_hosts()
    elif not bad and origin == "null":
        bad = True
    if bad:
        return JSONResponse({"detail": "Blocked: this request did not come from the Memoir app on this computer."}, status_code=403)
    return await call_next(request)
STATIC = pathlib.Path(__file__).parent / "static"
MEDIA = "('image','raw','video')"
REASON_GROUPS = {
    "missing": ("missing", "placeholder_date"),
    "mismatch": ("exif_vs_sidecar", "filename_vs_exif", "forward_date"),
    "corrupt": ("corrupt",),
}


# ------------------------------------------------------------------ health / sources
@app.get("/api/health")
def health():
    try:
        import pillow_heif  # noqa: F401
        heif = True
    except Exception:
        heif = False
    return {"version": __version__, "exiftool": exif.available(), "ffmpeg": bool(shutil.which("ffmpeg")),
            "heif": heif, "platform": platform.system(), "home": str(config.home()),
            "sep": os.sep}


@app.get("/api/summary")
def get_summary():
    s = scan.summary()
    pending = db.one(f"SELECT COUNT(*) c FROM media WHERE kind IN {MEDIA} AND scanned=0 AND hidden=0")["c"]
    srcs = db.one("SELECT COUNT(*) c, COALESCE(SUM(size),0) s FROM sources")
    unindexed = db.one("SELECT COUNT(*) c FROM sources WHERE state IN ('queued','offline')")["c"]
    return {**s, "pending_scan": pending, "sources": srcs["c"], "source_bytes": srcs["s"], "unindexed_sources": unindexed,
            "similar_ready": db.one("SELECT COUNT(*) c FROM media WHERE phash IS NOT NULL")["c"] > 0}


@app.get("/api/sources")
def get_sources():
    return scan.list_sources()


@app.post("/api/sources")
def post_sources(body: dict = Body(...)):
    paths = body.get("paths") or []
    if not paths:
        raise HTTPException(400, "No paths given.")
    return scan.add_sources(paths)


@app.post("/api/sources/{sid}/relink")
def post_relink(sid: int, body: dict = Body(...)):
    try:
        return scan.relink(sid, body.get("path", ""))
    except KeyError:
        raise HTTPException(404, "Source not found")
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/sources/{sid}")
def delete_source(sid: int):
    s = db.one("SELECT path FROM sources WHERE id=?", (sid,))
    if not s:
        raise HTTPException(404, "Source not found")
    if jobs.manager.active():
        raise HTTPException(409, "Wait for the running job to finish first.")
    sources.drop_zip(s["path"])
    db.run("DELETE FROM dup_choice WHERE media_id IN (SELECT id FROM media WHERE source_id=?)", (sid,))
    db.run("DELETE FROM media WHERE source_id=?", (sid,))
    db.run("DELETE FROM sources WHERE id=?", (sid,))
    return {"ok": True}


@app.get("/api/takeout-sets")
def get_sets():
    return scan.takeout_sets()


@app.get("/api/fs")
def fs_list(path: str = ""):
    """Server-side folder browser (the API only listens on this computer)."""
    if not path:
        roots = []
        if os.name == "nt":
            roots = [{"name": f"{c}:\\", "path": f"{c}:\\", "type": "dir"} for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
        else:
            home = str(pathlib.Path.home())
            roots = [{"name": "Home", "path": home, "type": "dir"}, {"name": "/", "path": "/", "type": "dir"}]
            for base in ("/Volumes", "/media", "/run/media", "/mnt"):
                if os.path.isdir(base):
                    try:
                        for n in sorted(os.listdir(base)):
                            full = os.path.join(base, n)
                            if os.path.isdir(full):
                                roots.append({"name": f"{n} ({base})", "path": full, "type": "dir"})
                    except OSError:
                        pass
        return {"path": "", "parent": None, "entries": roots}
    p = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(p):
        raise HTTPException(404, "Folder not found. Is the drive connected?")
    entries = []
    try:
        with os.scandir(p) as it:
            for e in it:
                if e.name.startswith("."):
                    continue
                try:
                    if e.is_dir(follow_symlinks=False):
                        entries.append({"name": e.name, "path": e.path, "type": "dir"})
                    elif e.name.lower().endswith(".zip"):
                        entries.append({"name": e.name, "path": e.path, "type": "zip", "size": e.stat().st_size})
                except OSError:
                    continue
    except PermissionError:
        raise HTTPException(403, "No permission to read this folder.")
    entries.sort(key=lambda x: (x["type"] != "dir", x["name"].lower()))
    parent = os.path.dirname(p)
    return {"path": p, "parent": parent if parent != p else "", "entries": entries[:3000]}


# ------------------------------------------------------------------ jobs
@app.get("/api/jobs")
def list_jobs():
    return jobs.manager.list()


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    j = jobs.manager.get(jid)
    if not j:
        raise HTTPException(404, "Job not found")
    return j.to_dict()


@app.post("/api/jobs")
def start_job(body: dict = Body(...)):
    t = body.get("type")
    params = {}
    if t == "scan":
        fn = scan.run_pipeline
    elif t == "similar":
        fn = duplicates.compute_phash
    elif t == "export":
        opts, resume = body.get("options") or {}, body.get("resume_id")
        if not resume:
            try:
                pf = export.preflight(opts)
            except export.ExportError as e:
                raise HTTPException(400, {"errors": [str(e)]})
            if pf["errors"]:
                raise HTTPException(400, {"errors": pf["errors"]})
        params = {"resume_id": resume}

        def fn(job):
            export.start(job, opts, resume)
    else:
        raise HTTPException(400, "Unknown job type.")
    try:
        job = jobs.manager.start(t, fn, params)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return job.to_dict()


def _job(jid):
    j = jobs.manager.get(jid)
    if not j:
        raise HTTPException(404, "Job not found")
    return j


@app.post("/api/jobs/{jid}/pause")
def pause_job(jid: str):
    j = _job(jid)
    j.pause("Paused")
    return j.to_dict()


@app.post("/api/jobs/{jid}/resume")
def resume_job(jid: str):
    j = _job(jid)
    j.resume()
    return j.to_dict()


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: str):
    j = _job(jid)
    j.cancel()
    return j.to_dict()


# ------------------------------------------------------------------ media / timeline
def _where(kind=None, status=None, q=None, folder=None, source=None, fmt=None, dated=True):
    c = [f"m.kind IN {MEDIA}", "m.hidden=0", "m.excluded=0"]
    a = []
    if dated:
        c.append("m.ts IS NOT NULL")
    if kind:
        c.append("m.kind=?")
        a.append(kind)
    if status:
        c.append("m.status=?")
        a.append(status)
    if q:
        c.append("m.name LIKE ?")
        a.append(f"%{q}%")
    if folder:
        c.append("m.folder=?")
        a.append(folder)
    if source:
        c.append("m.source_id=?")
        a.append(source)
    if fmt:
        c.append("m.ext=?")
        a.append(fmt.lower().lstrip("."))
    return " AND ".join(c), a


def _item(r):
    res = db.jl(r.get("resolved"))
    return {"id": r["id"], "name": r["name"], "folder": r["folder"], "kind": r["kind"], "ext": r["ext"],
            "size": r["size"], "status": r["status"], "date": res["value"] if res else None,
            "date_source": res["source"] if res else None, "reasons": db.jl(r.get("reasons"), []),
            "live": r.get("live_pair") is not None, "width": r["width"], "height": r["height"]}


_ITEM_COLS = "m.id,m.name,m.folder,m.kind,m.ext,m.size,m.status,m.resolved,m.reasons,m.live_pair,m.width,m.height,m.ts"


@app.get("/api/timeline/days")
def timeline_days(kind: str | None = None, q: str | None = None, folder: str | None = None,
                  source: int | None = None, fmt: str | None = None, status: str | None = None):
    w, a = _where(kind, status, q, folder, source, fmt)
    rows = db.q(f"SELECT date(m.ts,'unixepoch') AS d, COUNT(*) AS c FROM media m WHERE {w} GROUP BY d ORDER BY d DESC", a)
    return {"days": rows, "total": sum(r["c"] for r in rows)}


@app.get("/api/media")
def list_media(offset: int = 0, limit: int = Query(200, le=1000), kind: str | None = None, q: str | None = None,
               folder: str | None = None, source: int | None = None, fmt: str | None = None, status: str | None = None):
    w, a = _where(kind, status, q, folder, source, fmt)
    rows = db.q(f"SELECT {_ITEM_COLS} FROM media m WHERE {w} ORDER BY m.ts DESC, m.id DESC LIMIT ? OFFSET ?", a + [limit, offset])
    return {"items": [_item(r) for r in rows], "offset": offset}


@app.get("/api/folders")
def list_folders():
    return db.q(f"SELECT folder, COUNT(*) AS count FROM media WHERE kind IN {MEDIA} AND hidden=0 GROUP BY folder ORDER BY count DESC LIMIT 500")


@app.get("/api/media/{mid}")
def media_detail(mid: int):
    r = db.one("SELECT m.*, s.path AS spath, s.kind AS skind FROM media m JOIN sources s ON s.id=m.source_id WHERE m.id=?", (mid,))
    if not r:
        raise HTTPException(404, "Not found")
    item = _item(r)
    pair = db.one("SELECT id,name,ext FROM media WHERE live_pair=? AND hidden=1", (mid,)) if r["live_pair"] is not None and not r["hidden"] else None
    return item | {
        "candidates": db.jl(r["cands"], []), "resolved": db.jl(r["resolved"]), "manual": db.jl(r["manual"]),
        "source_path": r["spath"], "inner": r["inner"], "sha256": r["sha256"], "has_sidecar": r["sidecar_id"] is not None,
        "error": r["error"], "live_video": pair,
    }


@app.get("/api/media/{mid}/preview")
def media_preview(mid: int, w: int = 480):
    try:
        data, ct = preview.get_preview(mid, w)
    except KeyError:
        raise HTTPException(404, "Not found")
    return Response(content=data, media_type=ct, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/media/{mid}/neighbors")
def media_neighbors(mid: int, n: int = 2):
    r = db.one("SELECT folder, name FROM media WHERE id=?", (mid,))
    if not r:
        raise HTTPException(404, "Not found")
    cols = "id,name,resolved,status"
    before = db.q(f"SELECT {cols} FROM media WHERE folder=? AND name<? AND kind IN {MEDIA} AND hidden=0 AND ts IS NOT NULL ORDER BY name DESC LIMIT ?", (r["folder"], r["name"], n))
    after = db.q(f"SELECT {cols} FROM media WHERE folder=? AND name>? AND kind IN {MEDIA} AND hidden=0 AND ts IS NOT NULL ORDER BY name LIMIT ?", (r["folder"], r["name"], n))
    out = list(reversed(before)) + after
    return [{"id": x["id"], "name": x["name"], "date": (db.jl(x["resolved"]) or {}).get("value")} for x in out]


# ------------------------------------------------------------------ review
def _review_where(reason=None):
    c = ["m.status='review'", "m.hidden=0", f"m.kind IN {MEDIA}"]
    a = []
    if reason and reason in REASON_GROUPS:
        c.append("(" + " OR ".join("m.reasons LIKE ?" for _ in REASON_GROUPS[reason]) + ")")
        a += [f'%"{x}"%' for x in REASON_GROUPS[reason]]
    return " AND ".join(c), a


@app.get("/api/review/counts")
def review_counts():
    out = {}
    for g in ("all", *REASON_GROUPS):
        w, a = _review_where(None if g == "all" else g)
        out[g] = db.one(f"SELECT COUNT(*) c FROM media m WHERE {w}", a)["c"]
    out["orphans"] = db.one("SELECT COUNT(*) c FROM media WHERE kind='sidecar' AND status='orphan'")["c"]
    return out


@app.get("/api/review")
def review_list(reason: str | None = None, offset: int = 0, limit: int = Query(100, le=500)):
    w, a = _review_where(reason)
    rows = db.q(f"SELECT {_ITEM_COLS} FROM media m WHERE {w} ORDER BY m.id LIMIT ? OFFSET ?", a + [limit, offset])
    return {"items": [_item(r) for r in rows], "offset": offset}


@app.get("/api/review/orphans")
def review_orphans(limit: int = 300):
    return db.q("SELECT m.id, m.name, m.folder, s.path AS source FROM media m JOIN sources s ON s.id=m.source_id "
                "WHERE m.kind='sidecar' AND m.status='orphan' ORDER BY m.folder, m.name LIMIT ?", (limit,))


def _ids_from(body):
    ids = body.get("ids")
    if ids:
        return [int(i) for i in ids]
    qy = body.get("query")
    if qy is not None:
        w, a = _review_where(qy.get("reason"))
        if qy.get("folder"):
            w += " AND m.folder=?"
            a.append(qy["folder"])
        return [r["id"] for r in db.q(f"SELECT m.id FROM media m WHERE {w} ORDER BY m.name", a)]
    raise HTTPException(400, "Select files or give a query.")


def _parse_dt(date: str, time_: str):
    t = (time_ or "00:00:00").strip()
    if t.count(":") == 1:
        t += ":00"
    try:
        dt = datetime.fromisoformat(f"{date.strip()}T{t}")
    except ValueError:
        raise HTTPException(400, "Enter the date as YYYY-MM-DD and the time as HH:MM:SS.")
    if not (1990 <= dt.year <= datetime.now().year + 1):
        raise HTTPException(400, f"The year must be between 1990 and {datetime.now().year + 1}.")
    return dt


def _tz(v):
    if not v:
        return None
    if v == "Z" or (len(v) == 6 and v[0] in "+-" and v[3] == ":" and v[1:3].isdigit() and v[4:].isdigit()):
        return v
    raise HTTPException(400, "Timezone must look like +05:30.")


@app.post("/api/review/resolve")
def review_resolve(body: dict = Body(...)):
    ids = _ids_from(body)
    if not ids:
        raise HTTPException(400, "No files matched.")
    mode = body.get("mode", "set")
    ph = ",".join("?" * len(ids))
    rows = {r["id"]: r for r in db.q(f"SELECT id,name,manual,resolved,cands FROM media WHERE id IN ({ph})", ids)}
    new = {}
    if mode == "set":
        dt = _parse_dt(body.get("date", ""), body.get("time", "00:00:00"))
        tz = _tz(body.get("tz"))
        for i in ids:
            new[i] = {"value": dt.isoformat(), "tz": tz}
    elif mode == "candidate":
        idx = int(body.get("candidate", -1))
        for i in ids:
            c = db.jl(rows[i]["cands"], [])
            if not (0 <= idx < len(c)) or not c[idx].get("value"):
                raise HTTPException(400, "That candidate is not available.")
            new[i] = {"value": c[idx]["value"], "tz": c[idx].get("tz")}
    elif mode == "shift":
        mins = int(body.get("minutes", 0))
        for i in ids:
            res = db.jl(rows[i]["resolved"])
            if not res:
                raise HTTPException(400, "Some selected files have no date to shift. Set a date first.")
            new[i] = {"value": (datetime.fromisoformat(res["value"]) + timedelta(minutes=mins)).isoformat(), "tz": res.get("tz")}
    elif mode == "sequence":
        start = _parse_dt(body.get("date", ""), body.get("time", "00:00:00"))
        step = max(0, int(body.get("step_seconds", 1)))
        tz = _tz(body.get("tz"))
        for n, i in enumerate(sorted(ids, key=lambda k: rows[k]["name"].lower())):
            new[i] = {"value": (start + timedelta(seconds=step * n)).isoformat(), "tz": tz}
    elif mode == "clear":
        new = {i: None for i in ids}
    else:
        raise HTTPException(400, "Unknown mode.")
    batch = (db.one("SELECT COALESCE(MAX(batch),0) b FROM edits")["b"]) + 1
    db.many("INSERT INTO edits(batch, media_id, prev) VALUES(?,?,?)", [(batch, i, rows[i]["manual"]) for i in ids])
    db.many("UPDATE media SET manual=? WHERE id=?", [(json.dumps(v) if v else None, i) for i, v in new.items()])
    scan.recompute(ids)
    return {"updated": len(ids), "batch": batch}


@app.post("/api/review/undo")
def review_undo():
    b = db.one("SELECT MAX(batch) b FROM edits")["b"]
    if not b:
        raise HTTPException(404, "Nothing to undo.")
    rows = db.q("SELECT media_id, prev FROM edits WHERE batch=?", (b,))
    db.many("UPDATE media SET manual=? WHERE id=?", [(r["prev"], r["media_id"]) for r in rows])
    scan.recompute([r["media_id"] for r in rows])
    db.run("DELETE FROM edits WHERE batch=?", (b,))
    return {"undone": len(rows)}


# ------------------------------------------------------------------ duplicates
@app.get("/api/duplicates/summary")
def dup_summary():
    return duplicates.summary()


@app.get("/api/duplicates")
def dup_list(kind: str = "exact", offset: int = 0, limit: int = Query(20, le=100)):
    if kind == "similar":
        g = duplicates.similar_groups()
        return {"groups": g[offset:offset + limit], "total": len(g)}
    groups = duplicates.exact_groups(offset, limit)
    total = db.one("SELECT COUNT(*) c FROM dup_index")["c"]
    return {"groups": groups, "total": total}


@app.post("/api/duplicates/choice")
def dup_choice(body: dict = Body(...)):
    try:
        duplicates.set_choice(int(body["media_id"]), body.get("role", "keep"))
    except (KeyError, ValueError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/duplicates/plan")
def dup_plan(body: dict = Body(default={})):
    return duplicates.preview_plan(body.get("folders") or None)


@app.post("/api/duplicates/apply")
def dup_apply(body: dict = Body(...)):
    if not body.get("confirm"):
        raise HTTPException(400, "Confirmation required.")
    try:
        return duplicates.apply_plan(body.get("mode", "exclude"), body.get("folders") or None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/duplicates/reset")
def dup_reset():
    duplicates.reset_exclusions()
    return {"ok": True}


# ------------------------------------------------------------------ export
@app.post("/api/export/preflight")
def export_preflight(body: dict = Body(...)):
    try:
        return export.preflight(body)
    except export.ExportError as e:
        return {"ok": False, "errors": [str(e)], "warnings": [], "files": 0, "bytes": 0, "skipped": {}}


@app.get("/api/exports")
def list_exports():
    rows = db.q("SELECT e.id, e.created, e.dest, e.state, "
                "(SELECT COUNT(*) FROM export_items i WHERE i.export_id=e.id) AS total, "
                "(SELECT COUNT(*) FROM export_items i WHERE i.export_id=e.id AND i.state='done') AS done "
                "FROM exports e ORDER BY e.id DESC LIMIT 20")
    for r in rows:
        r["options"] = json.loads(db.one("SELECT options FROM exports WHERE id=?", (r["id"],))["options"])
    return rows


@app.get("/api/cache")
def cache_info():
    return {"bytes": preview.cache_size(), "limit": config.thumb_cache_limit()}


@app.post("/api/cache/clear")
def cache_clear():
    return {"removed": preview.clear_cache()}


# ------------------------------------------------------------------ web UI
if (STATIC / "index.html").exists():
    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (STATIC / full_path).resolve()
        if full_path and f.is_file() and STATIC.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
