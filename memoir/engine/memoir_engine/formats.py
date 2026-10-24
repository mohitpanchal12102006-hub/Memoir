"""Supported formats."""
import os

IMAGE = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff", "avif", "heic", "heif"}
RAW = {"dng", "cr2", "cr3", "nef", "arw", "orf", "rw2", "raf", "pef", "srw"}
VIDEO = {"mp4", "mov", "mkv", "avi", "webm", "3gp", "m4v", "mts", "m2ts", "mp", "mpg", "mpeg"}
STILL_FOR_LIVE = {"heic", "heif", "jpg", "jpeg"}
VIDEO_FOR_LIVE = {"mov", "mp4", "mp"}
IGNORED_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}


def ext_of(name: str) -> str:
    return os.path.splitext(name)[1].lower().lstrip(".")


def kind_of(name: str) -> str:
    """image | raw | video | sidecar | other"""
    e = ext_of(name)
    if e in IMAGE:
        return "image"
    if e in RAW:
        return "raw"
    if e in VIDEO:
        return "video"
    if e == "json":
        return "sidecar"
    return "other"


def is_ignored(inner: str) -> bool:
    parts = inner.replace("\\", "/").split("/")
    if parts[0] == "__MACOSX":
        return True
    return parts[-1].lower() in IGNORED_NAMES or parts[-1].startswith("._")
