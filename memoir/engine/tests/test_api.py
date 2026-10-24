import os
import time

import pytest
from fastapi.testclient import TestClient

import synth
from memoir_engine import jobs
from memoir_engine.api import app


@pytest.fixture()
def client(env):
    jobs.manager.jobs.clear()
    with TestClient(app, base_url="http://127.0.0.1:8787") as c:
        yield c


def wait(c, job, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        j = c.get(f"/api/jobs/{job['id']}").json()
        if j["state"] in ("done", "error", "cancelled"):
            return j
        time.sleep(0.2)
    raise AssertionError("job timeout")


def scan_all(c, env):
    s = synth.build(str(env / "data"))
    r = c.post("/api/sources", json={"paths": [s["z1"], s["z3"], s["loose"]]})
    assert r.status_code == 200 and not r.json()["errors"]
    j = c.post("/api/jobs", json={"type": "scan"}).json()
    j = wait(c, j)
    assert j["state"] == "done", j
    return s


def test_health_sources_scan(client, env):
    h = client.get("/api/health").json()
    assert h["exiftool"] and h["ffmpeg"]
    r = client.post("/api/sources", json={"paths": [str(env / "nope")]}).json()
    assert r["errors"] and not r["added"]
    assert client.post("/api/sources", json={"paths": []}).status_code == 400
    s = scan_all(client, env)
    sets = client.get("/api/takeout-sets").json()
    assert sets[0]["missing"] == [2] and sets[0]["count"] == 2
    srcs = client.get("/api/sources").json()
    assert all(x["online"] for x in srcs) and {x["state"] for x in srcs} == {"indexed"}
    sm = client.get("/api/summary").json()
    assert sm["review"] >= 5 and sm["pending_scan"] == 0 and sm["images"] > 10
    # a second scan with nothing new finishes immediately and a running job blocks a second one
    j = client.post("/api/jobs", json={"type": "scan"}).json()
    wait(client, j)
    assert client.post("/api/jobs", json={"type": "bogus"}).status_code == 400


def test_timeline_media_preview(client, env):
    scan_all(client, env)
    d = client.get("/api/timeline/days").json()
    assert d["total"] > 10 and d["days"][0]["d"] >= d["days"][-1]["d"]
    items = client.get("/api/media", params={"offset": 0, "limit": 500}).json()["items"]
    assert len(items) == d["total"]
    assert all(items[i]["date"] >= items[i + 1]["date"] for i in range(len(items) - 1))
    assert not any(i["name"] == "IMG_0100.mov" for i in items)  # live video is hidden
    assert next(i for i in items if i["name"] == "IMG_0100.jpg")["live"] is True
    f = client.get("/api/media", params={"q": "clip"}).json()["items"]
    assert [i["name"] for i in f] == ["clip.mp4"]
    assert client.get("/api/media", params={"kind": "video"}).json()["items"]
    det = client.get(f"/api/media/{f[0]['id']}").json()
    assert det["candidates"] and det["resolved"]["source"] == "exif"
    p = client.get(f"/api/media/{f[0]['id']}/preview?w=480")
    assert p.status_code == 200 and p.headers["content-type"] == "image/jpeg"
    big = client.get(f"/api/media/{items[0]['id']}/preview?w=1600")
    assert big.status_code == 200
    assert client.get("/api/media/999999").status_code == 404
    nb = client.get(f"/api/media/{f[0]['id']}/neighbors").json()
    assert isinstance(nb, list) and len(nb) > 0


def test_review_flow(client, env):
    scan_all(client, env)
    counts = client.get("/api/review/counts").json()
    assert counts["all"] >= 5 and counts["missing"] >= 2 and counts["mismatch"] >= 1 and counts["corrupt"] >= 1
    nd = next(i for i in client.get("/api/review", params={"reason": "missing"}).json()["items"] if i["name"] == "nodate.jpg")
    # invalid input is rejected with a clear message
    bad = client.post("/api/review/resolve", json={"ids": [nd["id"]], "mode": "set", "date": "14-05-2023", "time": "11:02"})
    assert bad.status_code == 400 and "YYYY-MM-DD" in bad.json()["detail"]
    assert client.post("/api/review/resolve", json={"ids": [nd["id"]], "mode": "set", "date": "1850-01-01"}).status_code == 400
    assert client.post("/api/review/resolve", json={"ids": [nd["id"]], "mode": "set", "date": "2023-05-14", "tz": "IST"}).status_code == 400
    ok = client.post("/api/review/resolve", json={"ids": [nd["id"]], "mode": "set", "date": "2023-05-14", "time": "11:02", "tz": "+05:30"})
    assert ok.status_code == 200
    det = client.get(f"/api/media/{nd['id']}").json()
    assert det["status"] == "fixed" and det["date"] == "2023-05-14T11:02:00"
    # shift
    client.post("/api/review/resolve", json={"ids": [nd["id"]], "mode": "shift", "minutes": 90})
    assert client.get(f"/api/media/{nd['id']}").json()["date"] == "2023-05-14T12:32:00"
    # undo twice goes back to the original (missing)
    assert client.post("/api/review/undo").status_code == 200
    assert client.get(f"/api/media/{nd['id']}").json()["date"] == "2023-05-14T11:02:00"
    assert client.post("/api/review/undo").status_code == 200
    assert client.get(f"/api/media/{nd['id']}").json()["status"] == "review"
    assert client.post("/api/review/undo").status_code == 404
    # use a candidate (the conflicting photo: pick the sidecar value)
    conflict = next(i for i in client.get("/api/review", params={"reason": "mismatch"}).json()["items"] if i["name"] == "IMG_0002.jpg")
    cands = client.get(f"/api/media/{conflict['id']}").json()["candidates"]
    idx = next(k for k, c in enumerate(cands) if c["source"] == "sidecar")
    client.post("/api/review/resolve", json={"ids": [conflict["id"]], "mode": "candidate", "candidate": idx})
    assert client.get(f"/api/media/{conflict['id']}").json()["status"] == "fixed"
    # batch by query with sequence spacing
    r = client.post("/api/review/resolve", json={"query": {"reason": "corrupt"}, "mode": "sequence", "date": "2020-01-01", "time": "10:00:00", "step_seconds": 5})
    assert r.json()["updated"] >= 1
    assert client.get("/api/review/orphans").json() == []
    assert client.post("/api/review/resolve", json={"mode": "set", "date": "2020-01-01"}).status_code == 400


def test_duplicates_and_export(client, env):
    scan_all(client, env)
    s = client.get("/api/duplicates/summary").json()
    assert s["exact"]["groups"] == 1 and s["folders"][0]["folder"] == "Goa trip"
    g = client.get("/api/duplicates", params={"kind": "exact"}).json()
    assert g["total"] == 1 and {m["role"] for m in g["groups"][0]["members"]} == {"keep", "remove"}
    assert client.post("/api/duplicates/apply", json={"mode": "exclude"}).status_code == 400  # needs confirm
    assert client.post("/api/duplicates/apply", json={"mode": "delete", "confirm": True}).status_code == 400
    a = client.post("/api/duplicates/apply", json={"mode": "exclude", "folders": ["Goa trip"], "confirm": True}).json()
    assert a["excluded"] == 1 and os.path.exists(a["report"])
    # similar needs a job
    j = client.post("/api/jobs", json={"type": "similar"}).json()
    assert wait(client, j)["state"] == "done"
    assert client.get("/api/duplicates", params={"kind": "similar"}).status_code == 200

    out = str(env / "out")
    opts = {"destination": {"type": "folder", "path": out}, "structure": "year-month", "prefix": True, "sidecar_tz": "+05:30"}
    pf = client.post("/api/export/preflight", json=opts).json()
    assert pf["ok"] and pf["files"] > 10 and pf["filesystem"]
    # bad destination is rejected up front
    bad = client.post("/api/jobs", json={"type": "export", "options": {"destination": {"type": "folder", "path": os.path.join(str(env / "data"), "loose", "o")}}})
    assert bad.status_code == 400 and "inside a source folder" in bad.json()["detail"]["errors"][0]
    j = client.post("/api/jobs", json={"type": "export", "options": opts}).json()
    j = wait(client, j)
    assert j["state"] == "done" and j["result"]["failed"] == 0, j
    assert os.path.exists(os.path.join(out, "2023", "05", "2023-05-14_11-02-00_IMG_0001.jpg"))
    ex = client.get("/api/exports").json()
    assert ex[0]["state"] == "done" and ex[0]["done"] == ex[0]["total"]
    client.post("/api/duplicates/reset")
    assert client.get("/api/duplicates/summary").json()["folders"][0]["excluded"] == 0


def test_fs_relink_pause(client, env):
    s = scan_all(client, env)
    r = client.get("/api/fs", params={"path": str(env / "data")}).json()
    assert any(e["type"] == "zip" for e in r["entries"]) and r["parent"]
    assert client.get("/api/fs").json()["entries"]
    assert client.get("/api/fs", params={"path": str(env / "missing")}).status_code == 404
    # a folder with ZIP parts is expanded into its ZIP files
    sub = env / "zips"
    sub.mkdir()
    import shutil
    shutil.copy(s["z3"], sub / "takeout-20240101T000000Z-001.zip")
    added = client.post("/api/sources", json={"paths": [str(sub)]}).json()["added"]
    assert len(added) == 1 and added[0]["kind"] == "zip" and added[0]["part_no"] == 1
    # offline detection and relink
    zid = next(x["id"] for x in client.get("/api/sources").json() if x["path"] == s["z3"])
    moved = str(env / "moved.zip")
    os.rename(s["z3"], moved)
    st = {x["id"]: x for x in client.get("/api/sources").json()}[zid]
    assert st["online"] is False and st["state"] == "offline"
    assert client.post(f"/api/sources/{zid}/relink", json={"path": str(env / "nothing.zip")}).status_code == 400
    ok = client.post(f"/api/sources/{zid}/relink", json={"path": moved})
    assert ok.status_code == 200 and ok.json()["state"] == "indexed"
    assert client.delete(f"/api/sources/{zid}").status_code == 200
    assert client.delete(f"/api/sources/{zid}").status_code == 404


def test_only_this_computer_may_use_the_api(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health", headers={"Host": "evil.example.com"}).status_code == 403   # DNS rebinding
    ok = client.post("/api/sources", json={"paths": []}, headers={"Origin": "http://localhost:5173"})
    assert ok.status_code == 400  # allowed origin reaches the handler
    for origin in ("https://evil.example.com", "null"):
        r = client.post("/api/jobs", json={"type": "scan"}, headers={"Origin": origin})
        assert r.status_code == 403 and "Blocked" in r.json()["detail"]
    assert client.get("/api/fs", headers={"Origin": "https://evil.example.com"}).status_code == 403
