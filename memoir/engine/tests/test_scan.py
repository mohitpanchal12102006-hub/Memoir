import json

import synth
from memoir_engine import db, scan
from memoir_engine.jobs import Job


def by_name(name, folder=None):
    rows = db.q("SELECT * FROM media WHERE name=?", (name,))
    if folder:
        rows = [r for r in rows if r["folder"] == folder]
    assert rows, name
    return rows[0]


def run_all(paths):
    res = scan.add_sources(paths)
    assert not res["errors"], res
    job = Job("pipeline")
    job.state = "running"
    scan.run_pipeline(job)
    return job


def test_pipeline(env):
    s = synth.build(str(env / "data"))
    job = run_all([s["z1"], s["z3"], s["loose"]])
    # ignored files are not indexed
    assert db.one("SELECT COUNT(*) c FROM media WHERE name IN ('random.txt','metadata.json','._junk.jpg')")["c"] == 0

    r = by_name("IMG_0001.jpg", "Photos from 2023")
    assert r["status"] == "ok" and "tz_only" in json.loads(r["reasons"])
    assert json.loads(r["resolved"])["source"] == "exif"

    r = by_name("IMG_0002.jpg")  # sidecar in another part, conflicting
    assert r["sidecar_id"] is not None
    assert r["status"] == "review" and "exif_vs_sidecar" in json.loads(r["reasons"])

    r = by_name("IMG-20230514-WA0031.jpg")
    assert r["status"] == "ok" and json.loads(r["resolved"])["source"] == "filename"

    r = by_name("nodate.jpg")
    assert r["status"] == "review" and "missing" in json.loads(r["reasons"])

    assert json.loads(by_name("IMG_0003.jpg")["resolved"])["value"].startswith("2022-03-03")
    assert json.loads(by_name("IMG_0003(1).jpg")["resolved"])["value"].startswith("2022-03-04")
    assert by_name("IMG_0004-edited.jpg")["sidecar_id"] == by_name("IMG_0004.jpg")["sidecar_id"]
    long = by_name("a_very_long_photo_name_that_exceeds_the_limit_1234567890.jpg")
    assert json.loads(long["resolved"])["value"].startswith("2020-02-02")

    r = by_name("corrupt.jpg")
    assert r["status"] == "review" and "corrupt" in json.loads(r["reasons"])
    r = by_name("sentinel.jpg")
    assert r["status"] == "review" and "placeholder_date" in json.loads(r["reasons"])

    vid = by_name("clip.mp4")
    assert vid["status"] == "ok" and json.loads(vid["resolved"])["value"].startswith("2022-08-01T10:00")

    live = by_name("IMG_0100.jpg")
    mov = by_name("IMG_0100.mov")
    assert mov["live_pair"] == live["id"] and mov["hidden"] == 1 and live["hidden"] == 0
    assert mov["ts"] == live["ts"]

    assert json.loads(by_name("PXL_20240102_030405.jpg")["resolved"])["value"] == "2024-01-02T03:04:05"
    assert by_name("IMG_part3.jpg")["status"] == "ok"

    # exact duplicate across albums shares a hash
    a = by_name("IMG_0001.jpg", "Photos from 2023")
    b = by_name("IMG_0001.jpg", "Goa trip")
    assert a["sha256"] and a["sha256"] == b["sha256"]

    sets = scan.takeout_sets()
    assert sets[0]["missing"] == [2] and sets[0]["count"] == 2
    summ = job.result
    assert summ["review"] >= 5 and summ["total"] > 15
    assert db.one("SELECT COUNT(*) c FROM media WHERE kind='sidecar' AND status='orphan'")["c"] == 0


def test_manual_fix(env):
    s = synth.build(str(env / "data"))
    run_all([s["z1"], s["z3"]])
    r = by_name("nodate.jpg")
    db.run("UPDATE media SET manual=? WHERE id=?", (json.dumps({"value": "2023-05-14T11:02:00", "tz": None}), r["id"]))
    scan.recompute([r["id"]])
    r = by_name("nodate.jpg")
    assert r["status"] == "fixed" and r["ts"] is not None
