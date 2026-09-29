from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("minetrace.jobs")


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class Job:
    id: str
    name: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def create_job(name: str, func: Callable, *args: Any, **kwargs: Any) -> str:
    job_id = str(uuid.uuid4())
    job = Job(id=job_id, name=name)

    with _lock:
        _jobs[job_id] = job

    def _run():
        with _lock:
            job.status = JobStatus.RUNNING

        try:
            result = func(job, *args, **kwargs)
            with _lock:
                job.status = JobStatus.COMPLETED
                job.progress = 1.0
                job.result = result
                job.completed_at = datetime.now(timezone.utc)
        except Exception as e:
            logger.exception(f"Job {job_id} ({name}) failed")
            with _lock:
                job.status = JobStatus.FAILED
                job.error = str(e)
                job.completed_at = datetime.now(timezone.utc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return job_id


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def update_progress(job: Job, progress: float, message: str = "") -> None:
    with _lock:
        job.progress = progress
        job.message = message
