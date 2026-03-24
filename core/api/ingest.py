"""
ROSA OS — Universal Ingest API.

Endpoints for ingesting URLs, files, and raw text into the knowledge graph.
WebSocket for real-time job progress.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.ingest.job_queue import get_job_queue, JobStatus
from core.ingest.universal_ingester import ingest, ingest_bytes, ingest_text, detect_type

logger = logging.getLogger("rosa.api.ingest")

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


# ── REQUEST MODELS ─────────────────────────────────────────────────────────

class UrlIngestRequest(BaseModel):
    url: str
    hint: str = ""
    priority: str = "normal"
    metadata: dict = {}


class TextIngestRequest(BaseModel):
    text: str
    source: str = "manual"
    tags: list[str] = []


# ── ENDPOINTS ──────────────────────────────────────────────────────────────

@router.post("/url", status_code=202)
async def ingest_url(req: UrlIngestRequest):
    """Enqueue a URL for ingestion. Returns job ID immediately."""
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL must start with http:// or https://")
    try:
        job = await ingest(
            source=req.url,
            hint=req.hint,
            priority=req.priority,
            metadata=req.metadata,
        )
        return {"job_id": job.id, "type": job.type, "status": job.status.value}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/file", status_code=202)
async def ingest_file(file: UploadFile = File(...)):
    """Upload a file for ingestion. Returns job ID immediately."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    # Basic safety: block executables
    blocked_exts = {".exe", ".bat", ".cmd", ".ps1", ".sh", ".msi", ".dll"}
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix in blocked_exts:
        raise HTTPException(400, f"File type not allowed: {suffix}")

    data = await file.read()
    max_bytes = 5_000 * 1024 * 1024  # 5 GB
    if len(data) > max_bytes:
        raise HTTPException(413, f"File too large ({len(data) / 1e9:.1f} GB, max 5 GB)")

    try:
        job = await ingest_bytes(
            data=data,
            filename=file.filename,
            priority="normal",
            metadata={"original_filename": file.filename, "content_type": file.content_type},
        )
        return {"job_id": job.id, "type": job.type, "status": job.status.value, "filename": file.filename}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/text")
async def ingest_text_endpoint(req: TextIngestRequest):
    """Directly ingest raw text (synchronous, no queue)."""
    if not req.text.strip():
        raise HTTPException(400, "text cannot be empty")
    result = await ingest_text(req.text, source=req.source, tags=req.tags)
    return result.to_dict()


@router.post("/archive", status_code=202)
async def ingest_archive(file: UploadFile = File(...)):
    """Upload a ZIP/TAR archive for recursive ingestion."""
    if not file.filename:
        raise HTTPException(400, "No filename provided")
    suffix = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if suffix not in (".zip", ".tar", ".gz", ".bz2", ".xz"):
        raise HTTPException(400, "Only ZIP and TAR archives are supported")

    data = await file.read()
    try:
        job = await ingest_bytes(data=data, filename=file.filename, priority="low")
        return {"job_id": job.id, "type": "archive", "status": job.status.value}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/jobs")
async def list_jobs(status: Optional[str] = None):
    """List all ingest jobs, optionally filtered by status."""
    queue = get_job_queue()
    jobs = queue.list_jobs(status=status)
    return [j.to_dict() for j in jobs]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get details for a specific ingest job."""
    queue = get_job_queue()
    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return job.to_dict()


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a queued job."""
    queue = get_job_queue()
    job = queue.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job.status not in (JobStatus.QUEUED, JobStatus.RETRYING):
        raise HTTPException(409, f"Cannot cancel job in status: {job.status.value}")
    job.status = JobStatus.FAILED
    job.error = "Cancelled by user"
    return {"status": "cancelled", "job_id": job_id}


@router.get("/detect")
async def detect_ingest_type(source: str):
    """Detect what type of ingest handler would be used for a given source."""
    type_ = detect_type(source)
    return {"source": source, "detected_type": type_}


# ── WEBSOCKET ──────────────────────────────────────────────────────────────

@router.websocket("/ws")
async def ingest_ws(websocket: WebSocket):
    """
    WebSocket for real-time ingest job progress.
    Connect to receive updates for all jobs.
    """
    await websocket.accept()
    queue = get_job_queue()
    sub_queue = queue.subscribe()
    try:
        # Send current job state immediately
        jobs = queue.list_jobs()
        for job in jobs[-20:]:  # last 20 jobs
            await websocket.send_text(job.to_dict().__str__())
        import json
        for job in jobs[-20:]:
            await websocket.send_text(json.dumps(job.to_dict()))

        # Stream updates
        import asyncio
        while True:
            try:
                msg = await asyncio.wait_for(sub_queue.get(), timeout=30)
                await websocket.send_text(msg)
            except asyncio.TimeoutError:
                # Send ping to keep alive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("Ingest WS error: %s", exc)
    finally:
        queue.unsubscribe(sub_queue)
