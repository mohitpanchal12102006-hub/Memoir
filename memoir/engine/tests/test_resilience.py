import json
import os
import time
import zipfile

import synth
from memoir_engine import db, jobs, scan, sources
from memoir_engine.jobs import Job


def wait_state(job, states, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        if job.state in states:
            return
        time.sleep(0.05)
    raise AssertionError(f"job stuck in {job.state}: {job.message}")


def prep(env):
    jobs.manager.jobs.clear()
    s = synth.build(str(env / "data"))
    scan.add_sources([s["z1"], s["z3"]])
    j = Job("index")
    j.state = "running"
    scan.index_all(j)
    scan.match_all(j)
    return s


def test_drive_offline_pauses_then_resumes(env):
    s = prep(env)
    hidden = s["z1"] + ".hidden"
    sources.close_all()
    os.rename(s["z1"], hidden)  # the drive "disappears"
    job = jobs.manager.start("scan", scan.run_pipeline)
    wait_state(job, {"paused", "done", "error"})
    assert job.state == "paused" and "offline" in job.message.lower()
    st = {x["part_no"]: x for x in scan.list_sources()}
    assert st[1]["state"] == "offline" and st[1]["online"] is False
    os.rename(hidden, s["z1"])  # reconnect
    job.resume()
    wait_state(job, {"done", "error"})
    assert job.state == "done", job.error
    assert db.one("SELECT COUNT(*) c FROM media WHERE kind IN ('image','raw','video') AND hidden=0 AND scanned=0")["c"] == 0
    assert {x["state"] for x in scan.list_sources()} == {"indexed"}


def test_cancel_then_resume_scan(env):
    prep(env)
    job = Job("scan")
    job.state = "running"
    job.cancel()
    try:
        scan.deep_scan(job)
        raise AssertionError("expected cancellation")
    except jobs.Cancelled:
        pass
    assert db.one("SELECT COUNT(*) c FROM media WHERE scanned=1")["c"] == 0
    job2 = jobs.manager.start("scan", scan.run_pipeline)
    wait_state(job2, {"done", "error"})
    assert job2.state == "done"
    # running a second scan changes nothing and does not duplicate rows
    n = db.one("SELECT COUNT(*) c FROM media")["c"]
    job3 = jobs.manager.start("scan", scan.run_pipeline)
    wait_state(job3, {"done", "error"})
    assert db.one("SELECT COUNT(*) c FROM media")["c"] == n


def test_only_one_job_at_a_time(env):
    prep(env)
    job = jobs.manager.start("scan", scan.run_pipeline)
    try:
        jobs.manager.start("scan", scan.run_pipeline)
        second = True
    except RuntimeError:
        second = False
    wait_state(job, {"done", "error"})
    assert job.state == "done"
    assert second is False or job.state == "done"


def test_damaged_zip_and_bad_crc(env):
    root = env / "bad"
    root.mkdir()
    good = synth.build(str(env / "data"))
    # truncated ZIP (the download was cut short)
    cut = root / "takeout-20240101T000000Z-001.zip"
    data = open(good["z1"], "rb").read()
    cut.write_bytes(data[: len(data) // 2])
    res = scan.add_sources([str(cut), str(root / "missing.zip")])
    assert res["errors"] and not res["added"]  # not a valid ZIP at all, reported clearly
    # a ZIP whose stored file has flipped bytes: the CRC check catches it
    zpath = root / "crc.zip"
    payload = open(os.path.join(good["loose"], "PXL_20240102_030405.jpg"), "rb").read()
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        z.writestr("Takeout/Google Photos/Album/damaged.jpg", payload)
        z.writestr("Takeout/Google Photos/Album/fine.jpg", payload[:-1] + b"\x00")
    raw = bytearray(zpath.read_bytes())
    i = raw.find(payload[100:140])
    raw[i + 5] ^= 0xFF
    zpath.write_bytes(bytes(raw))
    scan.add_sources([str(zpath)])
    j = Job("scan")
    j.state = "running"
    scan.run_pipeline(j)
    rows = {r["name"]: r for r in db.q("SELECT * FROM media WHERE source_id=(SELECT id FROM sources WHERE path=?)", (str(zpath),))}
    assert rows["damaged.jpg"]["status"] == "review" and "corrupt" in json.loads(rows["damaged.jpg"]["reasons"])
    assert rows["fine.jpg"]["scanned"] == 1
    assert j.state == "running"  # one bad entry never stops the scan


def test_unicode_and_odd_names(env):
    root = env / "uni"
    root.mkdir()
    z = root / "takeout-20240101T000000Z-001.zip"
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), (9, 9, 9)).save(buf, "JPEG")
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Takeout/Google Photos/Photos from 2022/Ünïcödé 写真(1).jpg", buf.getvalue())
        zf.writestr("Takeout/Google Photos/Photos from 2022/Ünïcödé 写真.jpg.supplemental-metadata(1).json",
                    json.dumps({"photoTakenTime": {"timestamp": "1650000000"}}))
    scan.add_sources([str(z)])
    j = Job("scan")
    j.state = "running"
    scan.run_pipeline(j)
    r = db.one("SELECT * FROM media WHERE kind='image'")
    assert r["sidecar_id"] is not None and json.loads(r["resolved"])["value"].startswith("2022-04-15")
