import csv
import hashlib
import json
import os
import shutil
import subprocess
import time
import zipfile
from datetime import datetime

import pytest
from PIL import Image, ImageDraw

import synth
from memoir_engine import db, duplicates, exif, export, preview, scan
from memoir_engine.jobs import Job


def job():
    j = Job("t")
    j.state = "running"
    return j


def build_and_scan(env, extra=None):
    s = synth.build(str(env / "data"))
    paths = [s["z1"], s["z3"], s["loose"]] + (extra or [])
    scan.add_sources(paths)
    scan.run_pipeline(job())
    return s


def by_name(name, folder=None):
    rows = db.q("SELECT * FROM media WHERE name=?", (name,))
    if folder:
        rows = [r for r in rows if r["folder"] == folder]
    return rows[0]


def test_exact_duplicates_and_plan(env):
    build_and_scan(env)
    sm = duplicates.summary()
    assert sm["exact"]["groups"] == 1 and sm["exact"]["extra"] == 1
    assert [f["folder"] for f in sm["folders"]] == ["Goa trip"]
    g = duplicates.exact_groups()[0]
    roles = {m["folder"]: m["role"] for m in g["members"]}
    assert roles == {"Photos from 2023": "keep", "Goa trip": "remove"}
    goa = by_name("IMG_0001.jpg", "Goa trip")
    duplicates.set_choice(goa["id"], "keep")
    roles = {m["folder"]: m["role"] for m in duplicates.exact_groups()[0]["members"]}
    assert roles == {"Photos from 2023": "remove", "Goa trip": "keep"}
    duplicates.set_choice(goa["id"], "auto")
    plan = duplicates.preview_plan()
    assert plan["files"] == 1 and plan["folders"][0]["folder"] == "Goa trip"
    res = duplicates.apply_plan("exclude", ["Goa trip"])
    assert res["excluded"] == 1 and os.path.exists(res["report"])
    rows = list(csv.DictReader(open(res["report"], encoding="utf-8")))
    assert rows[0]["removed_from_folder"] == "Goa trip" and rows[0]["kept_folder"] == "Photos from 2023"
    assert by_name("IMG_0001.jpg", "Goa trip")["excluded"] == 1
    with pytest.raises(ValueError):
        duplicates.apply_plan("delete")


def test_quarantine_folder_source(env):
    s = build_and_scan(env)
    shutil.copy(os.path.join(s["loose"], "PXL_20240102_030405.jpg"), os.path.join(s["loose"], "copy.jpg"))
    scan.add_sources([s["loose"]])
    # re-index the folder source to pick the new file
    db.run("UPDATE sources SET state='queued' WHERE kind='folder'")
    scan.run_pipeline(job())
    res = duplicates.apply_plan("quarantine")
    assert res["quarantined"] == 1
    moved = [r for r in csv.DictReader(open(res["report"], encoding="utf-8")) if r["action"] == "quarantined"]
    assert len(moved) == 1
    assert not (os.path.exists(os.path.join(s["loose"], "copy.jpg")) and os.path.exists(os.path.join(s["loose"], "PXL_20240102_030405.jpg")))


def test_similar_images(env):
    s = build_and_scan(env)
    im = Image.new("RGB", (240, 180), (30, 30, 30))
    d = ImageDraw.Draw(im)
    for i in range(0, 240, 20):
        d.rectangle([i, (i * 7) % 150, i + 12, 180], fill=((i * 3) % 255, 120, (i * 5) % 255))
    d.ellipse([60, 40, 160, 140], fill=(250, 250, 10))
    im.save(os.path.join(s["loose"], "orig.jpg"), quality=92)
    im.resize((120, 90)).save(os.path.join(s["loose"], "small.jpg"), quality=70)
    db.run("UPDATE sources SET state='queued' WHERE kind='folder'")
    scan.run_pipeline(job())
    duplicates.compute_phash(job())
    groups = duplicates.similar_groups()
    names = [{m["name"] for m in g["members"]} for g in groups]
    assert {"orig.jpg", "small.jpg"} in names
    # nothing is removed automatically for similar groups
    g = next(g for g in groups if {m["name"] for m in g["members"]} == {"orig.jpg", "small.jpg"})
    assert all(m["role"] == "keep" for m in g["members"])
    assert max(g["members"], key=lambda m: m["width"] or 0)["name"] == "orig.jpg"


def test_previews(env):
    build_and_scan(env)
    data, ct = preview.get_preview(by_name("IMG_0001.jpg", "Photos from 2023")["id"], 480)
    assert ct == "image/jpeg" and Image.open(__import__("io").BytesIO(data)).size[0] <= 480
    data, ct = preview.get_preview(by_name("clip.mp4")["id"], 480)
    assert ct == "image/jpeg"
    data, ct = preview.get_preview(by_name("corrupt.jpg")["id"], 480)
    assert ct == "image/svg+xml" and b"JPG" in data
    assert preview.cache_size() > 0


def exif_dates(path):
    return {c["tag"]: (c["value"], c["tz"]) for c in exif.shared().read(path)["cands"]}


def framemd5(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "framemd5", "-"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return [l for l in r.stdout.splitlines() if not l.startswith("#")]


def test_export_folder_lossless(env):
    s = build_and_scan(env)
    duplicates.apply_plan("exclude", ["Goa trip"])
    out = str(env / "out")
    opts = {"destination": {"type": "folder", "path": out}, "structure": "year-month", "prefix": True,
            "sidecar_tz": "+05:30"}
    pf = export.preflight(opts)
    assert pf["ok"], pf["errors"]
    assert pf["skipped"]["removed_duplicates"] == 1 and pf["skipped"]["needs_review"] >= 1
    j = job()
    export.start(j, opts)
    assert j.result["failed"] == 0, j.result

    f1 = os.path.join(out, "2023", "05", "2023-05-14_11-02-00_IMG_0001.jpg")
    assert os.path.exists(f1)
    assert len([p for p in os.listdir(os.path.join(out, "2023", "05")) if "IMG_0001" in p]) == 1  # duplicate left out
    d = exif_dates(f1)
    assert d["EXIF:DateTimeOriginal"][0] == "2023-05-14T11:02:00"

    # sidecar-only photo: UTC 09:00 shown in the chosen timezone
    f3 = os.path.join(out, "2022", "03", "2022-03-03_14-30-00_IMG_0003.jpg")
    assert os.path.exists(f3)
    d = exif_dates(f3)
    assert d["EXIF:DateTimeOriginal"] == ("2022-03-03T14:30:00", "+05:30")

    # file system time equals the capture time
    assert abs(os.path.getmtime(f1) - time.mktime(datetime(2023, 5, 14, 11, 2, 0).timetuple())) < 2

    # pixel data identical to the original in the ZIP
    with zipfile.ZipFile(s["z1"]) as z:
        orig = z.read("Takeout/Google Photos/Photos from 2023/IMG_0001.jpg")
    open(str(env / "o.jpg"), "wb").write(orig)
    assert Image.open(str(env / "o.jpg")).tobytes() == Image.open(f1).tobytes()
    for p, name in ((str(env / "o.jpg"), "a.jpg"), (f1, "b.jpg")):
        subprocess.run(["exiftool", "-all=", "-o", str(env / name), p], capture_output=True, check=True)
    assert hashlib.sha256(open(str(env / "a.jpg"), "rb").read()).hexdigest() == hashlib.sha256(open(str(env / "b.jpg"), "rb").read()).hexdigest()

    # video: frames bit-identical, dates written
    fv = os.path.join(out, "2022", "08", "2022-08-01_15-30-00_clip.mp4")  # 10:00 UTC shown at +05:30
    assert os.path.exists(fv), os.listdir(os.path.join(out, "2022", "08"))
    with zipfile.ZipFile(s["z1"]) as z:
        open(str(env / "orig.mp4"), "wb").write(z.read("Takeout/Google Photos/Photos from 2023/clip.mp4"))
    assert framemd5(str(env / "orig.mp4")) == framemd5(fv)
    assert exif_dates(fv)["Keys:CreationDate"] == ("2022-08-01T15:30:00", "+05:30")

    # live photo pair exported together
    names = os.listdir(os.path.join(out, "2023", "08"))
    assert any(n.endswith("IMG_0100.jpg") for n in names) and any(n.endswith("IMG_0100.mov") for n in names)

    # review items are not exported by default
    all_files = [n for _d, _s, fs in os.walk(out) for n in fs]
    assert not any("nodate" in n or "corrupt" in n or "sentinel" in n or "IMG_0002" in n for n in all_files)
    assert not any(n.startswith(".memoir-") for n in all_files)
    assert os.path.exists(j.result["report"])

    # resume: drop two finished items and re-run
    eid = j.result["export_id"]
    rows = db.q("SELECT media_id, dest_path FROM export_items WHERE export_id=? AND state='done' LIMIT 2", (eid,))
    keep_mtime = os.path.getmtime(f1)
    for r in rows:
        os.remove(os.path.join(out, *r["dest_path"].split("/")))
        db.run("UPDATE export_items SET state='pending' WHERE export_id=? AND media_id=?", (eid, r["media_id"]))
    j2 = job()
    export.start(j2, {}, resume_id=eid)
    assert j2.done == 2 and j2.result["failed"] == 0
    for r in rows:
        assert os.path.exists(os.path.join(out, *r["dest_path"].split("/")))


def test_export_zip_and_options(env):
    s = build_and_scan(env)
    dest = str(env / "archive.zip")
    opts = {"destination": {"type": "zip", "path": dest}, "structure": "year", "prefix": False,
            "include_review": True, "unresolved": "folder"}
    pf = export.preflight(opts)
    assert pf["ok"], pf["errors"]
    j = job()
    export.start(j, opts)
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        names = z.namelist()
        assert "_Unsorted/nodate.jpg" in names and "_Unsorted/corrupt.jpg" in names
        info = z.getinfo("2023/IMG_0001.jpg") if "2023/IMG_0001.jpg" in names else z.getinfo("2023/IMG_0001_1.jpg")
        assert info.date_time[:5] == (2023, 5, 14, 11, 2)
        assert info.compress_type == zipfile.ZIP_STORED
    assert not os.path.exists(dest + ".partial")
    # overwrite protection and destination inside a source folder
    assert not export.preflight(opts)["ok"]
    bad = export.preflight({"destination": {"type": "folder", "path": os.path.join(s["loose"], "out")}})
    assert any("inside a source folder" in e for e in bad["errors"])
