"""Google Takeout sidecar matching.

Handles: <name>.json, <name>.supplemental-metadata.json (and truncated forms),
numbered duplicates (IMG(1).jpg <-> IMG.jpg(1).json), '-edited' photos and
names truncated by Takeout's length limit.
"""
import re

_SPLIT = re.compile(r"^(.*?)(\.supp[a-z\-]*)?(\((\d+)\))?$", re.I)
_EDITED = re.compile(r"-edited(?=\.[^.]+$|$)", re.I)


def sidecar_title(json_name: str) -> str:
    stem = json_name[:-5] if json_name.lower().endswith(".json") else json_name
    m = _SPLIT.match(stem)
    title, n = m.group(1), m.group(4)
    if n:
        if "." in title:
            root, ext = title.rsplit(".", 1)
            title = f"{root}({n}).{ext}"
        else:
            title = f"{title}({n})"
    return title


def media_keys(name: str):
    keys = [name.lower()]
    stripped = _EDITED.sub("", name)
    if stripped.lower() != name.lower():
        keys.append(stripped.lower())
    return keys


def match(media, sidecars):
    """media/sidecars: lists of dicts with id, name, dirkey. Returns ({media_id: sidecar_id}, orphan_sidecar_ids)."""
    by_dir = {}
    for s in sidecars:
        by_dir.setdefault(s["dirkey"], []).append(s)
    media_by_dir = {}
    for m in media:
        media_by_dir.setdefault(m["dirkey"], []).append(m)
    result, used = {}, set()
    for dirkey, group in by_dir.items():
        titles = {}
        for s in group:
            titles.setdefault(sidecar_title(s["name"]).lower(), s["id"])
        trunc = [(t, sid) for t, sid in titles.items() if len(t) >= 38]
        for m in media_by_dir.get(dirkey, []):
            sid = None
            for k in media_keys(m["name"]):
                if k in titles:
                    sid = titles[k]
                    break
            if sid is None and trunc:
                low = m["name"].lower()
                cands = [s for t, s in trunc if low.startswith(t)]
                if len(set(cands)) == 1:
                    sid = cands[0]
            if sid is not None:
                result[m["id"]] = sid
                used.add(sid)
    orphans = [s["id"] for s in sidecars if s["id"] not in used]
    return result, orphans
