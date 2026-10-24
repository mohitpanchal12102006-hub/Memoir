"""Filesystem helpers: location, filesystem type, free space, timestamps."""
from __future__ import annotations

import os
import shutil
import sys
import time
from datetime import datetime


def location_of(path: str) -> str:
    p = os.path.abspath(path)
    if os.name == "nt":
        sysdrive = os.environ.get("SystemDrive", "C:").upper()
        return "internal" if os.path.splitdrive(p)[0].upper() == sysdrive else "external"
    for pre in ("/Volumes/", "/media/", "/run/media/", "/mnt/"):
        if p.startswith(pre):
            return "external"
    return "internal"


def _existing_parent(path: str) -> str:
    p = os.path.abspath(path)
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return p


def fs_type(path: str) -> str:
    try:
        import psutil
    except ImportError:
        return "unknown"
    p = os.path.realpath(_existing_parent(path))
    best, best_len = "unknown", -1
    for part in psutil.disk_partitions(all=True):
        mp = part.mountpoint
        if os.name == "nt":
            ok = p.lower().startswith(mp.lower())
        else:
            ok = p == mp or p.startswith(mp.rstrip("/") + "/")
        if ok and len(mp) > best_len:
            best, best_len = (part.fstype or "unknown").lower(), len(mp)
    return best


def free_bytes(path: str) -> int:
    return shutil.disk_usage(_existing_parent(path)).free


def same_device(a: str, b: str) -> bool:
    try:
        return os.stat(_existing_parent(a)).st_dev == os.stat(_existing_parent(b)).st_dev
    except OSError:
        return False


def is_fat(fs: str) -> bool:
    return fs in ("vfat", "fat", "fat32", "msdos")


def _win_set_creation(path: str, epoch: float) -> bool:
    import ctypes
    from ctypes import wintypes

    k = ctypes.windll.kernel32
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                              wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k.CreateFileW.restype = wintypes.HANDLE
    k.SetFileTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                              ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    k.SetFileTime.restype = wintypes.BOOL
    k.CloseHandle.argtypes = [wintypes.HANDLE]
    h = k.CreateFileW(path, 0x100, 3, None, 3, 0x02000000, None)
    if h == wintypes.HANDLE(-1).value or h is None:
        return False
    try:
        ft = int((epoch + 11644473600) * 10_000_000)
        ctime = wintypes.FILETIME(ft & 0xFFFFFFFF, ft >> 32)
        return bool(k.SetFileTime(h, ctypes.byref(ctime), None, None))
    finally:
        k.CloseHandle(h)


def local_epoch(local_iso: str) -> float:
    """Capture time (naive local clock time) as an epoch for file timestamps."""
    dt = datetime.fromisoformat(local_iso)
    return time.mktime(dt.timetuple())


def set_file_times(path: str, local_iso: str) -> dict:
    """Set modified time and, where the OS allows, creation time to the capture time."""
    t = local_epoch(local_iso)
    os.utime(path, (t, t))
    res = {"mtime": True, "birthtime": "unsupported"}
    if os.name == "nt":
        try:
            res["birthtime"] = "set" if _win_set_creation(path, t) else "failed"
        except Exception:
            res["birthtime"] = "failed"
    elif sys.platform == "darwin":
        res["birthtime"] = "via-mtime"  # macOS moves the creation date back when mtime is set earlier
    return res
