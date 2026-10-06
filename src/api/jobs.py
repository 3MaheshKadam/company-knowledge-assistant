"""Bounded background job queue (producer/consumer) for slow work such as document ingestion.

* Bounded: a full queue rejects new work (backpressure -> HTTP 503) instead of exhausting memory.
* Workers are threads; job state lives in memory. To scale out, replace with Celery/RQ + Redis
  behind the same submit()/get() interface.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

QUEUED, RUNNING, DONE, FAILED = "queued", "running", "done", "failed"


class QueueFull(Exception):
    pass


@dataclass
class Job:
    id: str
    kind: str
    status: str = QUEUED
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobQueue:
    def __init__(self, workers: int = 2, max_size: int = 100, retain: int = 1000) -> None:
        self._q: queue.Queue[tuple[Job, Callable[[], dict[str, Any]]] | None] = queue.Queue(max_size)
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._retain = retain
        self._n_workers = workers
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for i in range(self._n_workers):
            t = threading.Thread(target=self._run, name=f"job-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self, timeout: float = 5.0) -> None:
        for _ in self._threads:
            self._q.put(None)
        for t in self._threads:
            t.join(timeout)
        self._threads.clear()

    def submit(self, kind: str, fn: Callable[[], dict[str, Any]]) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind)
        try:
            self._q.put_nowait((job, fn))
        except queue.Full as exc:
            raise QueueFull("job queue is full") from exc
        with self._lock:
            self._jobs[job.id] = job
            self._evict()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(reversed(self._jobs.values()))  # newest first

    def depth(self) -> int:
        return self._q.qsize()

    def _evict(self) -> None:
        while len(self._jobs) > self._retain:
            oldest_id, oldest = next(iter(self._jobs.items()))
            if oldest.status in (QUEUED, RUNNING):
                break
            del self._jobs[oldest_id]

    def _run(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            job, fn = item
            job.status = RUNNING
            try:
                job.result = fn()
                job.status = DONE
            except Exception as exc:  # noqa: BLE001 - job failures must never kill the worker
                job.error = f"{type(exc).__name__}: {exc}"[:500]
                job.status = FAILED
            finally:
                job.finished_at = time.time()
