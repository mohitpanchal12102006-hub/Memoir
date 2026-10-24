"""ExifTool wrapper (persistent process) for reading and losslessly writing metadata."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from datetime import datetime

from . import config, dates

_CHARSET = ["-charset", "filename=utf8"]


def _tool_dirs():
    here = os.path.dirname(os.path.abspath(__file__))
    return [str(config.home() / "tools"), os.path.normpath(os.path.join(here, "..", "..", "tools")),
            os.path.normpath(os.path.join(here, "..", "tools"))]


def find_exiftool():
    """MEMOIR_EXIFTOOL, then a 'tools' folder next to the app, then PATH."""
    env = os.environ.get("MEMOIR_EXIFTOOL")
    if env and os.path.exists(env):
        return env
    for d in _tool_dirs():
        for name in ("exiftool.exe", "exiftool", "exiftool(-k).exe"):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    for name in ("exiftool", "exiftool.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def available() -> bool:
    return find_exiftool() is not None


class ExifToolError(RuntimeError):
    pass


class ExifTool:
    def __init__(self):
        self.exe = find_exiftool()
        self.proc = None
        self.lock = threading.Lock()
        self.out_q: queue.Queue = queue.Queue()
        self.err_q: queue.Queue = queue.Queue()

    # --- process management -------------------------------------------------
    def _pump(self, stream, q):
        for raw in iter(stream.readline, b""):
            q.put(raw.decode("utf-8", "replace").rstrip("\r\n"))
        q.put(None)

    def _start(self):
        if not self.exe:
            raise ExifToolError("exiftool was not found. Install it from https://exiftool.org and make sure it is on PATH.")
        flags = 0
        if os.name == "nt":
            flags = 0x08000000  # CREATE_NO_WINDOW
        self.proc = subprocess.Popen(
            [self.exe, "-stay_open", "True", "-@", "-"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags,
        )
        self.out_q, self.err_q = queue.Queue(), queue.Queue()
        threading.Thread(target=self._pump, args=(self.proc.stdout, self.out_q), daemon=True).start()
        threading.Thread(target=self._pump, args=(self.proc.stderr, self.err_q), daemon=True).start()

    def close(self):
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.stdin.write(b"-stay_open\nFalse\n")
                    self.proc.stdin.flush()
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.kill()
            self.proc = None

    def execute(self, args, timeout=600):
        """Run one command. Returns (stdout, stderr) text."""
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                self._start()
            data = "\n".join(list(args) + ["-echo4", "{ready_err}", "-execute"]) + "\n"
            try:
                self.proc.stdin.write(data.encode("utf-8"))
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self.proc = None
                raise ExifToolError("exiftool process died")
            out, err = [], []
            for q_, buf, token in ((self.out_q, out, "{ready}"), (self.err_q, err, "{ready_err}")):
                while True:
                    try:
                        line = q_.get(timeout=timeout)
                    except queue.Empty:
                        self.proc.kill()
                        self.proc = None
                        raise ExifToolError("exiftool timed out")
                    if line is None:
                        self.proc = None
                        raise ExifToolError("exiftool process ended unexpectedly")
                    if line == token:
                        break
                    buf.append(line)
            return "\n".join(out), "\n".join(err)

    # --- reading -------------------------------------------------------------
    def read(self, path: str) -> dict:
        args = _CHARSET + [
            "-j", "-G1", "-FileType", "-Error", "-Warning", "-ImageWidth", "-ImageHeight",
            "-DateTimeOriginal", "-CreateDate", "-CreationDate", "-MediaCreateDate", "-TrackCreateDate",
            "-OffsetTimeOriginal", "-OffsetTimeDigitized", path,
        ]
        out, _ = self.execute(args)
        info = {"cands": [], "width": None, "height": None, "error": None}
        offsets = {}
        try:
            data = json.loads(out)[0]
        except (ValueError, IndexError):
            info["error"] = "unreadable"
            return info
        for key, val in data.items():
            if key == "SourceFile" or ":" not in key:
                continue
            group, tag = key.rsplit(":", 1)
            if tag == "Error":
                info["error"] = str(val)
            elif tag == "FileType" and str(val).upper() in ("TXT", "UNKNOWN"):
                info["error"] = "not a valid media file"
            elif tag in ("OffsetTimeOriginal", "OffsetTimeDigitized"):
                if isinstance(val, str) and len(val) == 6 and val[0] in "+-" and val[3] == ":":
                    offsets[tag] = val
            elif tag == "ImageWidth" and info["width"] is None and isinstance(val, int):
                info["width"] = val
            elif tag == "ImageHeight" and info["height"] is None and isinstance(val, int):
                info["height"] = val
            else:
                c = dates.embedded_candidate(group, tag, val)
                if c:
                    info["cands"].append(c)
        for c in info["cands"]:
            if c.get("tz") is None and not c.get("bad"):
                if c["tag"] == "EXIF:DateTimeOriginal" and "OffsetTimeOriginal" in offsets:
                    c["tz"] = offsets["OffsetTimeOriginal"]
                elif c["tag"] == "EXIF:CreateDate" and "OffsetTimeDigitized" in offsets:
                    c["tz"] = offsets["OffsetTimeDigitized"]
        return info

    # --- writing -------------------------------------------------------------
    def write_dates(self, path: str, kind: str, local_iso: str, tz: str | None):
        """Write the capture date into the file's metadata. Returns (ok, message)."""
        dt = datetime.fromisoformat(local_iso)
        local = dt.strftime("%Y:%m:%d %H:%M:%S")
        off = "+00:00" if tz == "Z" else tz
        args = _CHARSET + ["-overwrite_original", "-m"]
        if kind == "video":
            delta = dates.tz_delta(tz)
            utc = (dt - delta) if delta is not None else dt
            u = utc.strftime("%Y:%m:%d %H:%M:%S")
            args += ["-api", "QuickTimeUTC=1"]
            for t in ("QuickTime:CreateDate", "QuickTime:ModifyDate", "TrackCreateDate", "TrackModifyDate",
                      "MediaCreateDate", "MediaModifyDate"):
                args.append(f"-{t}={u}")
            args.append(f"-Keys:CreationDate={local}{off or '+00:00'}")
        else:
            args += [f"-AllDates={local}", f"-XMP:CreateDate={local}{off or ''}"]
            if off:
                args += [f"-OffsetTimeOriginal={off}", f"-OffsetTimeDigitized={off}", f"-OffsetTime={off}"]
        args.append(path)
        out, err = self.execute(args)
        ok = any(line.strip().startswith(("1 image files updated", "1 files updated")) or "files updated" in line and not line.strip().startswith("0")
                 for line in out.splitlines())
        msg = " ".join(x for x in (err.strip(), out.strip()) if x)
        return ok, msg

    def preview_bytes(self, path: str):
        """Extract an embedded preview JPEG (RAW and some others). Returns bytes or None."""
        if not self.exe:
            return None
        for tag in ("PreviewImage", "JpgFromRaw", "OtherImage", "ThumbnailImage"):
            try:
                r = subprocess.run([self.exe] + _CHARSET + ["-b", f"-{tag}", path], capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                return None
            if r.returncode == 0 and len(r.stdout) > 500 and r.stdout[:2] == b"\xff\xd8":
                return r.stdout
        return None


_shared = None
_shared_lock = threading.Lock()


def shared() -> ExifTool:
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = ExifTool()
        return _shared


def shutdown():
    global _shared
    with _shared_lock:
        if _shared is not None:
            _shared.close()
            _shared = None
