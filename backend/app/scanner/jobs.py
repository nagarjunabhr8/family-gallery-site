"""Background job queue: one worker thread runs scan and analysis jobs in order.

A finished scan automatically chains an analysis job (pHash, quality, duplicates).
"""

import logging
import queue
import threading

from sqlalchemy import select, update

from ..db import SessionLocal
from ..models import ScanJob
from .scan import create_job, run_scan

log = logging.getLogger(__name__)

ACTIVE = ("queued", "running")


class ScanManager:
    def __init__(self) -> None:
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        # Jobs left running by a previous process can't resume
        with SessionLocal() as s:
            s.execute(
                update(ScanJob)
                .where(ScanJob.status.in_(ACTIVE))
                .values(status="interrupted", message="App stopped during this job")
            )
            s.commit()
        self._thread = threading.Thread(target=self._worker, name="job-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._cancel.set()
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=10)

    def enqueue(self, folder_id: int | None = None, kind: str = "scan") -> ScanJob:
        """Queue a job, or return the already active one."""
        with SessionLocal() as s:
            active = s.scalars(
                select(ScanJob).where(ScanJob.status.in_(ACTIVE)).order_by(ScanJob.id)
            ).first()
            if active:
                return active
            job = create_job(s, folder_id, kind)
        self._queue.put(job.id)
        return job

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self, job_id: int) -> None:
        from ..analysis.run import run_analysis  # heavy imports (onnxruntime) only when needed

        with SessionLocal() as s:
            job = s.get(ScanJob, job_id)
            kind = job.kind
            # Queue the follow-up analysis up front so the UI never sees an idle gap
            follow = create_job(s, job.folder_id, "analyze") if kind == "scan" else None
        self._cancel.clear()
        log.info("%s job %s started", kind, job_id)
        if kind == "analyze":
            job = run_analysis(job_id, self._cancel)
        else:
            job = run_scan(job_id, self._cancel)
        log.info("%s job %s finished: %s", kind, job_id, job.status)

        if follow is not None:
            if job.status == "done":
                self._run(follow.id)
            else:
                with SessionLocal() as s:
                    s.get(ScanJob, follow.id).status = "cancelled"
                    s.commit()

    def _worker(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            try:
                self._run(job_id)
            except Exception:
                log.exception("Job %s crashed", job_id)


manager = ScanManager()
