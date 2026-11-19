"""Background job execution: in-process pool or durable Redis queue."""
from __future__ import annotations

import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from .config import settings
from .db import engine
from .models import Job, UsageEvent
from .progress import hub
from .storage import job_dir, sync_to_s3
from .processing.pipeline import run_job


def _emit(job_id: str, status: str, progress: int, message: str) -> None:
    hub.publish(job_id, {"job_id": job_id, "status": status,
                         "progress": progress, "message": message})


def execute(job_id: str, user_id: int, mode: str, input_path: Path, params: dict) -> None:
    """Run one job end-to-end. Safe to call from a worker process."""
    with Session(engine) as session:
        job = session.exec(select(Job).where(Job.id == job_id)).first()
        if not job:
            return
        job.status = "running"
        job.progress = 1
        job.message = "Starting…"
        job.updated_at = datetime.now(timezone.utc)
        session.add(job)
        session.commit()
        _emit(job_id, "running", 1, "Starting…")

        def cb(pct: int, msg: str) -> None:
            with Session(engine) as s:
                j = s.exec(select(Job).where(Job.id == job_id)).first()
                if j:
                    j.progress = pct
                    j.message = msg
                    j.updated_at = datetime.now(timezone.utc)
                    s.add(j)
                    s.commit()
            _emit(job_id, "running", pct, msg)

        try:
            out_dir = job_dir(user_id, job_id)
            result = run_job(mode, input_path, out_dir, params, cb)
            output_name = result.get("video") or result.get("pose") or result.get("point_cloud")
            sync_to_s3(user_id, job_id)
            job.status = "completed"
            job.progress = 100
            job.message = "Complete"
            job.output_filename = output_name
            job.result_json = json.dumps(result)
            job.updated_at = datetime.now(timezone.utc)
            session.add(job)
            session.add(UsageEvent(
                user_id=user_id, job_id=job_id,
                seconds=float(result.get("duration_seconds", 0.0)), mode=mode,
            ))
            session.commit()
            _emit(job_id, "completed", 100, "Complete")
        except Exception as exc:  # pragma: no cover
            traceback.print_exc()
            job.status = "failed"
            job.error = str(exc)[:1000]
            job.message = "Failed"
            job.updated_at = datetime.now(timezone.utc)
            session.add(job)
            session.commit()
            _emit(job_id, "failed", job.progress, job.message)


class JobManager:
    def __init__(self) -> None:
        self.pool = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS, thread_name_prefix="job")

    def submit(self, job_id: str, user_id: int, mode: str, input_path: Path, params: dict) -> None:
        if settings.queue_backend == "redis":
            from .queue import enqueue
            enqueue(job_id, user_id, mode, input_path, params, priority=params.get("priority", 0))
        else:
            self.pool.submit(execute, job_id, user_id, mode, input_path, params)


manager = JobManager()
