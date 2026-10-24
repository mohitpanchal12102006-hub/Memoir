"""Paths and settings. Everything lives under MEMOIR_HOME (default ~/.memoir)."""
import os
import pathlib


def home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("MEMOIR_HOME") or (pathlib.Path.home() / ".memoir"))


def db_path() -> pathlib.Path:
    return home() / "catalog.db"


def thumbs_dir() -> pathlib.Path:
    return home() / "thumbs"


def tmp_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("MEMOIR_TMP") or (home() / "tmp"))


def reports_dir() -> pathlib.Path:
    return home() / "reports"


def thumb_cache_limit() -> int:
    return int(os.environ.get("MEMOIR_THUMB_CACHE_MB", "1024")) * 1024 * 1024


def ensure() -> None:
    for p in (home(), thumbs_dir(), tmp_dir(), reports_dir()):
        p.mkdir(parents=True, exist_ok=True)
