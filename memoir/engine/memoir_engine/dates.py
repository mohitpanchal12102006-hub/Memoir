"""Date extraction and the resolution waterfall.

Priority: embedded metadata > Takeout sidecar > filename. Conflicts and missing
dates are flagged for review.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

MIN_YEAR = 1990
BLOCKING = {"missing", "placeholder_date", "exif_vs_sidecar", "filename_vs_exif", "forward_date", "corrupt"}


def _max_year() -> int:
    return datetime.now().year + 1


def year_ok(y: int) -> bool:
    return MIN_YEAR <= y <= _max_year()


_EXIF_RE = re.compile(
    r"^(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:[.,]\d+)?\s*(Z|[+-]\d{2}:?\d{2})?$"
)


def parse_exif(s):
    """Parse an ExifTool date string. Returns {'value','tz'} or None."""
    if not isinstance(s, str):
        return None
    m = _EXIF_RE.match(s.strip())
    if not m:
        return None
    y, mo, d, h, mi, se = (int(x) for x in m.groups()[:6])
    try:
        dt = datetime(y, mo, d, h, mi, se)
    except ValueError:
        return None
    tz = m.group(7)
    if tz and tz != "Z" and ":" not in tz:
        tz = tz[:3] + ":" + tz[3:]
    return {"value": dt.isoformat(), "tz": tz}


def tz_delta(tz):
    if not tz:
        return None
    if tz == "Z":
        return timedelta(0)
    sign = 1 if tz[0] == "+" else -1
    return sign * timedelta(hours=int(tz[1:3]), minutes=int(tz[4:6]))


def naive_epoch(value: str) -> float:
    """Epoch seconds treating the naive value as UTC (used only for ordering)."""
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


def epoch_to_naive(sec: float) -> str:
    return datetime.fromtimestamp(sec, timezone.utc).replace(tzinfo=None).isoformat()


# (rank, tag label, assumes UTC)
def embedded_candidate(group: str, tag: str, raw):
    """Build an embedded-date candidate from an ExifTool -G1 key. Returns None if not a date tag we use."""
    g = group
    rank, label, utc = None, None, False
    if tag == "DateTimeOriginal":
        if g.startswith(("ExifIFD", "IFD0", "EXIF")):
            rank, label = 1, "EXIF:DateTimeOriginal"
        elif g.startswith("XMP"):
            rank, label = 3, "XMP:DateTimeOriginal"
        else:
            rank, label = 3, f"{g}:DateTimeOriginal"
    elif tag == "CreateDate":
        if g.startswith(("ExifIFD", "IFD0", "EXIF")):
            rank, label = 2, "EXIF:CreateDate"
        elif g.startswith("XMP"):
            rank, label = 3, "XMP:CreateDate"
        elif g.startswith("QuickTime"):
            rank, label, utc = 4, "QuickTime:CreateDate", True
        else:
            rank, label = 4, f"{g}:CreateDate"
    elif tag == "CreationDate":
        if g.startswith("Keys"):
            rank, label = 1, "Keys:CreationDate"
        elif g.startswith("QuickTime"):
            rank, label = 2, "QuickTime:CreationDate"
    elif tag == "MediaCreateDate":
        rank, label, utc = 5, "QuickTime:MediaCreateDate", True
    elif tag == "TrackCreateDate":
        rank, label, utc = 5, "QuickTime:TrackCreateDate", True
    if rank is None:
        return None
    parsed = parse_exif(raw)
    cand = {"source": "exif", "tag": label, "rank": rank}
    if parsed is None:
        if isinstance(raw, str) and raw.strip():
            cand.update({"value": None, "tz": None, "bad": True, "raw": raw})
            return cand
        return None
    dt = datetime.fromisoformat(parsed["value"])
    cand["value"] = parsed["value"]
    cand["tz"] = parsed["tz"] or ("Z" if utc else None)
    if not year_ok(dt.year):
        cand["bad"] = True
    return cand


def sidecar_candidate(ts_seconds):
    try:
        sec = float(ts_seconds)
        value = epoch_to_naive(sec)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    cand = {"source": "sidecar", "tag": "photoTakenTime", "value": value, "tz": "Z", "rank": 6}
    if not year_ok(int(value[:4])):
        cand["bad"] = True
    return cand


_FN = [
    ("wa", re.compile(r"(?:IMG|VID|PTT|AUD|DOC)-(\d{4})(\d{2})(\d{2})-WA\d+", re.I), 3),
    ("std", re.compile(r"Screen ?Shot (\d{4})-(\d{2})-(\d{2}) at (\d{1,2})\.(\d{2})\.(\d{2})", re.I), 6),
    ("std", re.compile(r"Screenshot[_ ](\d{4})-(\d{2})-(\d{2})[-_ ](\d{2})[-.](\d{2})[-.](\d{2})", re.I), 6),
    ("std", re.compile(r"(?<!\d)(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})[-_ T.]?(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})(?!\d)"), 6),
    ("std", re.compile(r"(?<!\d)(\d{4})[-_.](\d{2})[-_.](\d{2})(?!\d)"), 3),
]
_EPOCH = re.compile(r"(?<!\d)(1\d{9})(\d{3})?(?!\d)")


def filename_candidate(name: str):
    """Parse a capture date from a platform filename. Returns a candidate or None."""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    for kind, rx, n in _FN:
        m = rx.search(stem)
        if not m:
            continue
        nums = [int(x) for x in m.groups()]
        try:
            if n == 3:
                dt = datetime(nums[0], nums[1], nums[2])
                approx = True
            else:
                dt = datetime(*nums[:6])
                approx = False
        except ValueError:
            continue
        if not year_ok(dt.year):
            continue
        return {"source": "filename", "tag": "filename", "value": dt.isoformat(), "tz": None,
                "approx": approx, "kind": kind, "rank": 7}
    m = _EPOCH.search(stem)
    if m:
        sec = int(m.group(1))
        try:
            value = epoch_to_naive(sec)
        except (OverflowError, OSError, ValueError):
            return None
        if year_ok(int(value[:4])):
            return {"source": "filename", "tag": "filename-epoch", "value": value, "tz": "Z",
                    "approx": False, "kind": "std", "rank": 7}
    return None


def resolve(cands, manual=None, has_error=False):
    """Return (resolved|None, status, reasons, ts|None)."""
    if manual:
        r = {"value": manual["value"], "tz": manual.get("tz"), "source": "manual", "tag": "manual"}
        return r, "fixed", [], naive_epoch(r["value"])

    reasons = []
    emb = [c for c in cands if c["source"] == "exif"]
    valid = [c for c in emb if not c.get("bad")]
    bad = [c for c in emb if c.get("bad")]
    sc = next((c for c in cands if c["source"] == "sidecar" and not c.get("bad")), None)
    fn = next((c for c in cands if c["source"] == "filename"), None)
    primary = min(valid, key=lambda c: c["rank"]) if valid else None
    res = primary or sc or fn

    if has_error and not valid:
        reasons.append("corrupt")
    if res is None:
        reasons.append("missing")
        if bad or any(c["source"] == "sidecar" and c.get("bad") for c in cands):
            reasons.append("placeholder_date")
    else:
        if primary and sc:
            sc_utc = naive_epoch(sc["value"])
            pd = tz_delta(primary.get("tz"))
            if pd is not None:
                d = abs(naive_epoch(primary["value"]) - pd.total_seconds() - sc_utc)
                if d > 86400:
                    reasons.append("exif_vs_sidecar")
            else:
                d = abs(naive_epoch(primary["value"]) - sc_utc)
                if d > 86400:
                    reasons.append("exif_vs_sidecar")
                elif d > 120:
                    r = d % 900
                    if r <= 120 or r >= 780:
                        reasons.append("tz_only")
        if fn and res is not fn:
            dd = abs((datetime.fromisoformat(fn["value"]).date() - datetime.fromisoformat(res["value"]).date()).days)
            if dd > 1:
                reasons.append("forward_date" if fn.get("kind") == "wa" else "filename_vs_exif")

    status = "review" if any(r in BLOCKING for r in reasons) else "ok"
    resolved = None
    if res is not None:
        resolved = {"value": res["value"], "tz": res.get("tz"), "source": res["source"], "tag": res.get("tag")}
    ts = naive_epoch(resolved["value"]) if resolved else None
    return resolved, status, reasons, ts
