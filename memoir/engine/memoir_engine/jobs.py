"""Background jobs with pause / resume / cancel."""
from __future__ import annotations

import threading
import time
import traceback
import uuid


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, type_: str, params: dict | None = None):
        self.id = uuid.uuid4().hex[:8]
        self.type = type_
        self.params = params or {}
        self.state = "queued"
        self.stage = ""
        self.message = ""
        self.done = 0
        self.total = 0
        self.bytes_done = 0
        self.bytes_total = 0
        self.started = None
        self.finished = None
        self.error = None
        self.result: dict = {}
        self._go = threading.Event()
        self._go.set()
        self._cancel = False
        self._paused_for = 0.0
        self._pause_started = None

    def checkpoint(self):
        if self._cancel:
            raise Cancelled()
        if not self._go.is_set():
            self._go.wait()
        if self._cancel:
            raise Cancelled()

    def add_bytes(self, n: int):
        self.bytes_done += n

    def pause(self, message: str = ""):
        if self.state == "running":
            self._go.clear()
            self.state = "paused"
            self._pause_started = time.time()
            if message:
                self.message = message

    def resume(self):
        if self.state == "paused":
            if self._pause_started:
                self._paused_for += time.time() - self._pause_started
                self._pause_started = None
            self.state = "running"
            self._go.set()

    def cancel(self):
        self._cancel = True
        self._go.set()

    def to_dict(self):
        end = self.finished or time.time()
        active = (end - self.started - self._paused_for) if self.started else 0
        speed = (self.bytes_done / active) if active > 1 and self.bytes_done else 0
        eta = None
        if speed and self.bytes_total > self.bytes_done:
            eta = int((self.bytes_total - self.bytes_done) / speed)
        return {
            "id": self.id, "type": self.type, "state": self.state, "stage": self.stage, "message": self.message,
            "done": self.done, "total": self.total, "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
            "mb_per_sec": round(speed / 1048576, 1) if speed else 0, "eta_sec": eta,
            "error": self.error, "result": self.result, "params": self.params,
        }


class Manager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def active(self):
        return next((j for j in self.jobs.values() if j.state in ("running", "paused", "queued")), None)

    def start(self, type_, fn, params=None):
        with self.lock:
            cur = self.active()
            if cur:
                raise RuntimeError(f"Another job is already {cur.state}: {cur.type}")
            job = Job(type_, params)
            self.jobs[job.id] = job

        def run():
            job.state = "running"
            job.started = time.time()
            try:
                fn(job)
                if job.state != "error":
                    job.state = "done"
            except Cancelled:
                job.state = "cancelled"
            except Exception as e:  # noqa: BLE001
                job.state = "error"
                job.error = f"{type(e).__name__}: {e}"
                job.message = job.error
                traceback.print_exc()
            finally:
                job.finished = time.time()

        threading.Thread(target=run, daemon=True, name=f"job-{job.id}").start()
        return job

    def get(self, job_id):
        return self.jobs.get(job_id)

    def list(self):
        return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: j.started or 0, reverse=True)]


manager = Manager()
