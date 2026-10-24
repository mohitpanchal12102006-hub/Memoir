"""Exact (SHA-256) and similar (perceptual hash) duplicate groups, keeper rules and removal plans."""
from __future__ import annotations

import csv
import io
import os
import re
import shutil
import time

from . import config, db, sources

MEDIA = "('image','raw','video')"
_YEAR_FOLDER = re.compile(r"^Photos from \d{4}$", re.I)
_sim_cache = {"key": None, "groups": []}
_idx = {"key": None}
_ver = [0]
_plan_cache = {"key": None, "val": None}


def _bump():
    _ver[0] += 1


def refresh_index(force: bool = False):
    """Keep a small table of every hash that appears more than once."""
    k = db.one("SELECT COUNT(*) c, COALESCE(MAX(id),0) m FROM media WHERE sha256 IS NOT NULL AND hidden=0")
    key = (str(config.db_path()), k["c"], k["m"])
    if not force and _idx["key"] == key:
        return
    db.run("DELETE FROM dup_index")
    db.run(f"INSERT INTO dup_index(sha, c, sz) SELECT sha256, COUNT(*), MAX(size) FROM media "
           f"WHERE sha256 IS NOT NULL AND hidden=0 AND kind IN {MEDIA} GROUP BY sha256 HAVING COUNT(*)>1")
    _idx["key"] = key


def _folder_pref(folder: str) -> int:
    if _YEAR_FOLDER.match(folder or ""):
        return 3
    if folder in ("(root)", "", None):
        return 2
    return 1


def _score(m):
    return ((m["width"] or 0) * (m["height"] or 0), m["size"] or 0, m["has_exif"] or 0,
            _folder_pref(m["folder"]), -m["id"])


def _member(m):
    return {"id": m["id"], "name": m["name"], "folder": m["folder"], "size": m["size"],
            "width": m["width"], "height": m["height"], "has_exif": bool(m["has_exif"]),
            "source": os.path.basename(m["spath"]), "source_path": m["spath"], "inner": m["inner"],
            "status": m["status"], "excluded": bool(m["excluded"])}


def _assign_roles(members, choices, kind):
    """members: list of dict rows. Returns list of member dicts with role keep/remove."""
    best = max(members, key=_score)
    explicit_keep = [m for m in members if choices.get(m["id"]) == "keep"]
    explicit_remove = {m["id"] for m in members if choices.get(m["id"]) == "remove"}
    out = []
    if kind == "exact":
        keepers = {m["id"] for m in explicit_keep} or {best["id"]}
        for m in members:
            role = "keep" if m["id"] in keepers else "remove"
            out.append(dict(_member(m), role=role, suggested=(m["id"] == best["id"])))
    else:  # similar: nothing is removed unless explicitly chosen
        for m in members:
            role = "remove" if m["id"] in explicit_remove and m["id"] not in {x["id"] for x in explicit_keep} else "keep"
            out.append(dict(_member(m), role=role, suggested=(m["id"] == best["id"])))
        if all(x["role"] == "remove" for x in out):
            for x in out:
                if x["suggested"]:
                    x["role"] = "keep"
    out.sort(key=lambda x: (x["role"] != "keep", -x["id"]))
    return out


def _choices():
    return {r["media_id"]: r["role"] for r in db.q("SELECT media_id, role FROM dup_choice")}


_MEMBER_SQL = ("SELECT m.id, m.sha256, m.name, m.folder, m.size, m.width, m.height, m.status, m.excluded, m.inner,"
               " m.has_exif AS has_exif, s.path AS spath FROM media m JOIN sources s ON s.id=m.source_id")


def exact_groups(offset=0, limit=50):
    refresh_index()
    hashes = db.q("SELECT sha AS sha256, c, sz FROM dup_index ORDER BY (c-1)*sz DESC, sha LIMIT ? OFFSET ?", (limit, offset))
    if not hashes:
        return []
    ph = ",".join("?" * len(hashes))
    rows = db.q(_MEMBER_SQL + f" WHERE m.hidden=0 AND m.sha256 IN ({ph})", [h["sha256"] for h in hashes])
    by = {}
    for r in rows:
        by.setdefault(r["sha256"], []).append(r)
    ch = _choices()
    out = []
    for h in hashes:
        mem = by.get(h["sha256"], [])
        if len(mem) > 1:
            out.append({"id": "e-" + h["sha256"][:16], "kind": "exact", "reclaimable": (len(mem) - 1) * (h["sz"] or 0),
                        "members": _assign_roles(mem, ch, "exact")})
    return out


def _all_exact_plan():
    """All exact groups with roles (used for the folder breakdown and applying)."""
    refresh_index()
    key = (_idx["key"], _ver[0])
    if _plan_cache["key"] == key:
        return _plan_cache["val"]
    rows = db.q(_MEMBER_SQL + f" WHERE m.hidden=0 AND m.kind IN {MEDIA} AND m.sha256 IN (SELECT sha FROM dup_index)")
    by = {}
    for r in rows:
        by.setdefault(r["sha256"], []).append(r)
    ch = _choices()
    val = [(h, _assign_roles(mem, ch, "exact")) for h, mem in by.items() if len(mem) > 1]
    _plan_cache.update(key=key, val=val)
    return val


def summary():
    refresh_index()
    ex = db.one("SELECT COUNT(*) groups, COALESCE(SUM(c-1),0) extra, COALESCE(SUM((c-1)*sz),0) reclaimable FROM dup_index")
    sim = similar_groups()
    plan = _all_exact_plan()
    folders = {}
    for _h, members in plan:
        for m in members:
            if m["role"] == "remove":
                f = folders.setdefault(m["folder"], {"folder": m["folder"], "files": 0, "bytes": 0, "excluded": 0})
                f["files"] += 1
                f["bytes"] += m["size"] or 0
                f["excluded"] += 1 if m["excluded"] else 0
    keep_folders = {}
    for _h, members in plan:
        for m in members:
            if m["role"] == "keep":
                keep_folders[m["folder"]] = keep_folders.get(m["folder"], 0) + 1
    return {
        "exact": ex,
        "similar": {"groups": len(sim), "extra": sum(len(g["members"]) - 1 for g in sim),
                    "reclaimable": sum(sum(m["size"] or 0 for m in g["members"]) - max(m["size"] or 0 for m in g["members"]) for g in sim)},
        "folders": sorted(folders.values(), key=lambda f: -f["bytes"]),
        "keep_folders": [{"folder": k, "files": v} for k, v in sorted(keep_folders.items(), key=lambda kv: -kv[1])],
    }


# ---------------------------------------------------------------- similar images
def _open_image(src, inner, size):
    from PIL import Image
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    if size and size > 120 * 1024 * 1024:
        return None
    data = sources.read_bytes(src, inner)
    return Image.open(io.BytesIO(data))


def compute_phash(job):
    """dHash for images Pillow can open. Skips RAW and video."""
    from PIL import Image
    job.stage = "similar"
    rows = db.q("SELECT m.id, m.inner, m.size, m.source_id FROM media m WHERE m.kind='image' AND m.phash IS NULL "
                "AND m.hidden=0 AND m.scanned=1 ORDER BY m.source_id, m.id")
    job.total, job.done = len(rows), 0
    cache = {}
    upd = []
    for r in rows:
        job.checkpoint()
        src = cache.get(r["source_id"]) or cache.setdefault(r["source_id"], db.one("SELECT * FROM sources WHERE id=?", (r["source_id"],)))
        ph = ""
        try:
            im = _open_image(src, r["inner"], r["size"])
            if im is not None:
                im = im.convert("L").resize((9, 8), Image.LANCZOS)
                px = list(im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata())
                bits = 0
                for y in range(8):
                    for x in range(8):
                        bits = (bits << 1) | (1 if px[y * 9 + x] > px[y * 9 + x + 1] else 0)
                ph = f"{bits:016x}"
        except sources.SourceOffline:
            raise
        except Exception:
            ph = ""
        upd.append((ph or "none", r["id"]))
        job.done += 1
        if len(upd) >= 200:
            db.many("UPDATE media SET phash=? WHERE id=?", upd)
            upd = []
    if upd:
        db.many("UPDATE media SET phash=? WHERE id=?", upd)


def similar_groups(max_distance=6):
    rows = db.q("SELECT id, phash, sha256 FROM media WHERE phash IS NOT NULL AND phash!='none' AND hidden=0")
    key = (len(rows), max_distance)
    if _sim_cache["key"] == key:
        return _hydrate(_sim_cache["groups"])
    hv = {r["id"]: int(r["phash"], 16) for r in rows}
    sha = {r["id"]: r["sha256"] for r in rows}
    bands = [{} for _ in range(4)]
    for i, h in hv.items():
        for b in range(4):
            bands[b].setdefault((h >> (16 * b)) & 0xFFFF, []).append(i)
    parent = {i: i for i in hv}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for b in bands:
        for ids in b.values():
            if len(ids) < 2 or len(ids) > 300:
                continue
            for a in range(len(ids)):
                for c in range(a + 1, len(ids)):
                    x, y = ids[a], ids[c]
                    if bin(hv[x] ^ hv[y]).count("1") <= max_distance:
                        parent[find(x)] = find(y)
    clusters = {}
    for i in hv:
        clusters.setdefault(find(i), []).append(i)
    groups = [sorted(ids) for ids in clusters.values() if len(ids) > 1 and len({sha[i] for i in ids}) > 1]
    _sim_cache.update(key=key, groups=groups)
    return _hydrate(groups)


def _hydrate(groups):
    if not groups:
        return []
    ch = _choices()
    out = []
    for ids in groups:
        ph = ",".join("?" * len(ids))
        mem = db.q(_MEMBER_SQL + f" WHERE m.id IN ({ph})", ids)
        out.append({"id": f"s-{min(ids)}", "kind": "similar", "reclaimable": 0,
                    "members": _assign_roles(mem, ch, "similar")})
    out.sort(key=lambda g: -len(g["members"]))
    return out


# ---------------------------------------------------------------- choices and plans
def set_choice(media_id: int, role: str):
    if role not in ("keep", "remove", "auto"):
        raise ValueError("role must be keep, remove or auto")
    m = db.one("SELECT sha256 FROM media WHERE id=?", (media_id,))
    if not m:
        raise KeyError("media not found")
    _bump()
    if role == "auto":
        db.run("DELETE FROM dup_choice WHERE media_id=?", (media_id,))
        return
    if role == "keep" and m["sha256"]:  # choosing a keeper resets other explicit choices in an exact group
        db.run("DELETE FROM dup_choice WHERE media_id IN (SELECT id FROM media WHERE sha256=?)", (m["sha256"],))
    db.run("INSERT OR REPLACE INTO dup_choice(media_id, role) VALUES(?,?)", (media_id, role))


def _plan_items(folders, include_similar=True):
    items = []
    for _h, members in _all_exact_plan():
        keep = next((m for m in members if m["role"] == "keep"), None)
        for m in members:
            if m["role"] == "remove" and (not folders or m["folder"] in folders):
                items.append((m, keep))
    if include_similar:
        choices = _choices()
        for g in similar_groups():
            keep = next((m for m in g["members"] if m["role"] == "keep"), None)
            for m in g["members"]:
                if m["role"] == "remove" and (not folders or m["folder"] in folders) and choices.get(m["id"]) == "remove":
                    items.append((m, keep))
    return items


def preview_plan(folders=None):
    items = _plan_items(folders)
    per = {}
    for m, _k in items:
        f = per.setdefault(m["folder"], {"folder": m["folder"], "removing": 0, "bytes": 0})
        f["removing"] += 1
        f["bytes"] += m["size"] or 0
    return {"files": len(items), "bytes": sum(m["size"] or 0 for m, _ in items), "folders": list(per.values())}


def apply_plan(mode: str, folders=None):
    if mode not in ("exclude", "quarantine"):
        raise ValueError("Mode must be 'exclude' or 'quarantine'. Deleting from the source is not offered in this version.")
    items = _plan_items(folders)
    _bump()
    config.ensure()
    report = config.reports_dir() / f"removal-{time.strftime('%Y%m%d-%H%M%S')}.csv"
    moved = excluded = skipped = 0
    qroot = config.home() / "quarantine" / time.strftime("%Y%m%d-%H%M%S")
    with open(report, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["action", "removed_from_folder", "removed_file", "removed_source", "kept_folder", "kept_file", "size", "note"])
        for m, keep in items:
            action, note = "excluded", ""
            if mode == "quarantine":
                src = db.one("SELECT * FROM sources WHERE id=(SELECT source_id FROM media WHERE id=?)", (m["id"],))
                if src and src["kind"] == "folder":
                    srcpath = sources.disk_path(src, m["inner"])
                    dest = qroot / m["inner"]
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(srcpath, str(dest))
                        action, note = "quarantined", str(dest)
                        moved += 1
                    except OSError as e:
                        note = f"could not move: {e}"
                        skipped += 1
                else:
                    note = "ZIP entries cannot be moved; excluded from export instead"
            db.run("UPDATE media SET excluded=1 WHERE id=?", (m["id"],))
            db.run("UPDATE media SET excluded=1 WHERE live_pair=? AND hidden=1", (m["id"],))
            excluded += 1
            w.writerow([action, m["folder"], m["name"], m["source_path"], keep["folder"] if keep else "",
                        keep["name"] if keep else "", m["size"], note])
    return {"excluded": excluded, "quarantined": moved, "skipped": skipped, "report": str(report)}


def reset_exclusions():
    _bump()
    db.run("UPDATE media SET excluded=0")
    db.run("DELETE FROM dup_choice")
