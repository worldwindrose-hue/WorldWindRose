"""
ROSA OS — Ingest Job Queue.

Async priority queue for heavy ingestion operations.
Jobs persist to disk and survive restarts.
Max 3 concurrent jobs. Auto-retry on failure (max 3 attempts).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger("rosa.ingest.queue")

_QUEUE_FILE = Path("memory/ingest_jobs.json")
_MAX_CONCURRENT = 3
_MAX_RETRIES = 3


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    RETRYING = "retrying"


class JobPriority(int, Enum):
    HIGH = 1
    NORMAL = 5
    LOW = 10


@dataclass
class IngestJob:
    id: str
    type: str          # youtube, pdf, github, url, file, text, archive, audio, image
    source: str        # URL or description
    status: JobStatus = JobStatus.QUEUED
    priority: JobPriority = JobPriority.NORMAL
    progress: int = 0  # 0-100
    result: Optional[dict] = None
    error: Optional[str] = None
    attempts: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["priority"] = self.priority.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "IngestJob":
        d = dict(d)
        d["status"] = JobStatus(d.get("status", "queued"))
        d["priority"] = JobPriority(d.get("priority", 5))
        return cls(**d)


# ── PERSISTENCE ───────────────────────────────────────────────────────────

def _load_jobs() -> dict[str, IngestJob]:
    if not _QUEUE_FILE.exists():
        return {}
    try:
        data = json.loads(_QUEUE_FILE.read_text())
        return {k: IngestJob.from_dict(v) for k, v in data.items()}
    except Exception as exc:
        logger.warning("Failed to load jobs: %s", exc)
        return {}


def _save_jobs(jobs: dict[str, IngestJob]) -> None:
    _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _QUEUE_FILE.write_text(
        json.dumps({k: v.to_dict() for k, v in jobs.items()}, indent=2, ensure_ascii=False)
    )


# ── JOB QUEUE ─────────────────────────────────────────────────────────────

class IngestJobQueue:
    """Priority queue for ingest jobs with persistence and concurrency control."""

    def __init__(self) -> None:
        self._jobs: dict[str, IngestJob] = {}
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self._handlers: dict[str, Callable] = {}
        self._ws_clients: list[asyncio.Queue] = []
        self._load()

    def _load(self) -> None:
        """Load persisted jobs; reset processing/retrying to queued."""
        self._jobs = _load_jobs()
        for job in self._jobs.values():
            if job.status in (JobStatus.PROCESSING, JobStatus.RETRYING):
                job.status = JobStatus.QUEUED
                job.progress = 0

    def register_handler(self, type_: str, handler: Callable) -> None:
        self._handlers[type_] = handler

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._ws_clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._ws_clients.discard(q) if hasattr(self._ws_clients, "discard") else None
        try:
            self._ws_clients.remove(q)
        except ValueError:
            pass

    async def _broadcast(self, job: IngestJob) -> None:
        msg = json.dumps(job.to_dict())
        for q in list(self._ws_clients):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def enqueue(
        self,
        type_: str,
        source: str,
        priority: JobPriority = JobPriority.NORMAL,
        metadata: Optional[dict] = None,
    ) -> IngestJob:
        job = IngestJob(
            id=str(uuid.uuid4()),
            type=type_,
            source=source,
            priority=priority,
            metadata=metadata or {},
        )
        self._jobs[job.id] = job
        _save_jobs(self._jobs)
        logger.info("Job enqueued: %s [%s] %s", job.id[:8], type_, source[:60])
        if self._running:
            asyncio.create_task(self._maybe_process())
        return job

    def get_job(self, job_id: str) -> Optional[IngestJob]:
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None) -> list[IngestJob]:
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status.value == status]
        return sorted(jobs, key=lambda j: (j.priority.value, j.created_at))

    def update_progress(self, job_id: str, progress: int, detail: str = "") -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        job.progress = min(100, max(0, progress))
        if detail:
            job.metadata["progress_detail"] = detail
        _save_jobs(self._jobs)
        try:
            asyncio.get_event_loop().create_task(self._broadcast(job))
        except RuntimeError:
            pass

    async def start(self) -> None:
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Ingest job queue started (max %d concurrent)", _MAX_CONCURRENT)

    async def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()

    async def _worker_loop(self) -> None:
        while self._running:
            await self._maybe_process()
            await asyncio.sleep(2)

    async def _maybe_process(self) -> None:
        queued = [j for j in self._jobs.values() if j.status == JobStatus.QUEUED]
        queued.sort(key=lambda j: (j.priority.value, j.created_at))
        for job in queued:
            asyncio.create_task(self._run_job(job))

    async def _run_job(self, job: IngestJob) -> None:
        async with self._semaphore:
            if job.status != JobStatus.QUEUED:
                return
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.now(timezone.utc).isoformat()
            job.attempts += 1
            _save_jobs(self._jobs)
            await self._broadcast(job)

            handler = self._handlers.get(job.type)
            if not handler:
                job.status = JobStatus.FAILED
                job.error = f"No handler for type: {job.type}"
                job.completed_at = datetime.now(timezone.utc).isoformat()
                _save_jobs(self._jobs)
                await self._broadcast(job)
                return

            try:
                from core.status.tracker import set_status, RosaStatus
                set_status(RosaStatus.ACTING, f"Изучаю: {job.source[:50]}")
            except Exception:
                pass

            try:
                result = await handler(job)
                job.status = JobStatus.DONE
                job.progress = 100
                job.result = result
                job.completed_at = datetime.now(timezone.utc).isoformat()
                logger.info("Job done: %s — %s", job.id[:8], result)
            except Exception as exc:
                logger.error("Job %s failed (attempt %d): %s", job.id[:8], job.attempts, exc)
                if job.attempts < _MAX_RETRIES:
                    job.status = JobStatus.QUEUED  # retry
                    job.error = str(exc)
                else:
                    job.status = JobStatus.FAILED
                    job.error = str(exc)
                    job.completed_at = datetime.now(timezone.utc).isoformat()

            _save_jobs(self._jobs)
            await self._broadcast(job)

            try:
                from core.status.tracker import set_status, RosaStatus
                set_status(RosaStatus.ONLINE, "Готова к работе")
            except Exception:
                pass


_queue: Optional[IngestJobQueue] = None


def get_job_queue() -> IngestJobQueue:
    global _queue
    if _queue is None:
        _queue = IngestJobQueue()
    return _queue
