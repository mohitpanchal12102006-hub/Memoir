import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMOIR_HOME", str(tmp_path / "home"))
    from memoir_engine import exif, sources
    yield tmp_path
    exif.shutdown()
    sources.close_all()
