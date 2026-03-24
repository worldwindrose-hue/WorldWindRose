"""
ROSA OS — Universal Ingester.

Detects any input type and routes it to the appropriate handler.
Every ingested item ends up in the knowledge graph + vector store.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from core.ingest.job_queue import get_job_queue, IngestJob, JobPriority

logger = logging.getLogger("rosa.ingest")

_MAX_FILE_BYTES = 5_000 * 1024 * 1024  # 5 GB limit

# ── TYPE DETECTION ────────────────────────────────────────────────────────

_URL_PATTERNS = {
    "youtube": re.compile(r"youtube\.com/watch|youtu\.be/|youtube\.com/playlist"),
    "github": re.compile(r"github\.com/[^/]+/[^/]+"),
    "arxiv": re.compile(r"arxiv\.org/(abs|pdf)/"),
    "tiktok": re.compile(r"tiktok\.com/@"),
    "twitter": re.compile(r"twitter\.com/|x\.com/"),
    "reddit": re.compile(r"reddit\.com/r/"),
    "wikipedia": re.compile(r"wikipedia\.org/wiki/"),
    "instagram": re.compile(r"instagram\.com/"),
}

_EXT_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".txt": "text",
    ".md": "text",
    ".csv": "spreadsheet",
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".json": "json",
    ".jsonl": "json",
    ".zip": "archive",
    ".tar": "archive",
    ".tar.gz": "archive",
    ".tgz": "archive",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".gif": "image",
    ".webp": "image",
    ".mp3": "audio",
    ".wav": "audio",
    ".ogg": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    ".mp4": "video",
    ".mkv": "video",
    ".avi": "video",
    ".mov": "video",
    ".epub": "epub",
    ".html": "html",
    ".htm": "html",
    ".py": "code",
    ".js": "code",
    ".ts": "code",
    ".go": "code",
    ".rs": "code",
    ".java": "code",
    ".cpp": "code",
    ".c": "code",
}

# Blocked for execution (read-only allowed)
_BLOCKED_EXEC = {".exe", ".sh", ".bat", ".cmd", ".ps1", ".msi"}


@dataclass
class IngestResult:
    type: str
    source: str
    nodes_created: int = 0
    chunks: int = 0
    summary: str = ""
    metadata: dict = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "source": self.source,
            "nodes_created": self.nodes_created,
            "chunks": self.chunks,
            "summary": self.summary,
            "metadata": self.metadata,
            "error": self.error,
        }


def detect_type(source: str) -> str:
    """Detect the ingest type from a URL, file path, or text hint."""
    s = source.strip()

    # URL detection
    if s.startswith("http://") or s.startswith("https://"):
        for type_, pattern in _URL_PATTERNS.items():
            if pattern.search(s):
                return type_
        return "url"

    # File path detection
    p = Path(s)
    suffix = p.suffix.lower()
    # Handle compound extensions
    if s.endswith(".tar.gz") or s.endswith(".tgz"):
        return "archive"
    if suffix in _BLOCKED_EXEC:
        return "blocked"
    if suffix in _EXT_MAP:
        return _EXT_MAP[suffix]

    # Fallback: treat as raw text
    return "text"


def detect_type_from_bytes(data: bytes, filename: str = "") -> str:
    """Detect type from file bytes + filename hint."""
    if filename:
        return detect_type(filename)
    # Try MIME sniffing
    mime, _ = mimetypes.guess_type(filename)
    if mime:
        if "pdf" in mime:
            return "pdf"
        if "zip" in mime or "tar" in mime:
            return "archive"
        if "audio" in mime:
            return "audio"
        if "video" in mime:
            return "video"
        if "image" in mime:
            return "image"
    # Magic bytes
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        return "archive"  # ZIP
    return "text"


# ── INGESTION CORE ────────────────────────────────────────────────────────

async def ingest(
    source: str,
    hint: str = "",
    priority: str = "normal",
    metadata: Optional[dict] = None,
) -> IngestJob:
    """
    Enqueue an ingest job for any source (URL, file path, or text).
    Returns the job immediately; processing happens in background.
    """
    type_ = hint or detect_type(source)
    if type_ == "blocked":
        raise ValueError(f"File type not allowed for execution: {source}")

    prio = JobPriority.HIGH if priority == "high" else JobPriority.NORMAL
    queue = get_job_queue()
    job = queue.enqueue(type_=type_, source=source, priority=prio, metadata=metadata or {})
    return job


async def ingest_bytes(
    data: bytes,
    filename: str,
    priority: str = "normal",
    metadata: Optional[dict] = None,
) -> IngestJob:
    """Ingest raw file bytes — saves to temp and enqueues."""
    import tempfile
    type_ = detect_type_from_bytes(data, filename)
    if type_ == "blocked":
        raise ValueError(f"File type blocked: {filename}")
    if len(data) > _MAX_FILE_BYTES:
        raise ValueError(f"File too large: {len(data) / 1e9:.1f} GB (max 5 GB)")

    # Save to temp file
    tmp = Path("memory/uploads") / filename
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(data)

    return await ingest(str(tmp), hint=type_, priority=priority, metadata=metadata)


async def ingest_text(
    text: str,
    source: str = "manual",
    tags: Optional[list[str]] = None,
) -> IngestResult:
    """Directly ingest raw text (no job queue — fast, synchronous)."""
    from core.ingest.handlers.text_handler import TextHandler
    handler = TextHandler()
    chunks = handler.chunk(text)
    nodes = await _save_chunks_to_graph(chunks, source=source, tags=tags or [])
    summary = await _summarize_ingest(source, nodes, type_="text")
    return IngestResult(
        type="text",
        source=source,
        nodes_created=nodes,
        chunks=len(chunks),
        summary=summary,
    )


# ── KNOWLEDGE GRAPH HELPERS ───────────────────────────────────────────────

async def _save_chunks_to_graph(
    chunks: list[str],
    source: str,
    tags: list[str] = None,
    extra_meta: dict = None,
) -> int:
    """Save text chunks to the knowledge graph. Returns number of nodes created."""
    if not chunks:
        return 0
    try:
        from core.memory.store import get_store
        store = await get_store()
        created = 0
        for chunk in chunks:
            if not chunk.strip():
                continue
            await store.add_insight(
                content=chunk,
                source_type="ingest",
                tags=tags or [],
                metadata={"source": source, **(extra_meta or {})},
            )
            created += 1
        logger.info("Saved %d nodes to knowledge graph (source: %s)", created, source[:60])
        return created
    except Exception as exc:
        logger.warning("Failed to save to graph: %s", exc)
        return 0


async def _summarize_ingest(source: str, nodes: int, type_: str) -> str:
    """Generate a brief summary of what was ingested."""
    return f"✅ Усвоила {type_} из {source[:60]}: добавлено {nodes} узлов в граф знаний"


async def post_ingest_analysis(job: IngestJob, result: IngestResult) -> str:
    """Rosa analyzes what she just learned and links to existing graph."""
    summary = result.summary or f"Усвоено {result.nodes_created} узлов из {result.source[:60]}"

    # Send web push notification
    try:
        from core.notifications.web_push import get_push_manager
        await get_push_manager().notify(
            title="🌹 ROSA — Данные усвоены",
            body=summary[:120],
            tag="ingest-done",
        )
    except Exception:
        pass

    return summary


# ── REGISTER HANDLERS WITH JOB QUEUE ─────────────────────────────────────

def _make_handler(handler_class):
    async def handler(job: IngestJob) -> dict:
        h = handler_class()
        result = await h.process(job)
        await post_ingest_analysis(job, result)
        return result.to_dict()
    return handler


def register_all_handlers() -> None:
    """Register all type handlers with the job queue."""
    queue = get_job_queue()
    try:
        from core.ingest.handlers.youtube_handler import YouTubeHandler
        queue.register_handler("youtube", _make_handler(YouTubeHandler))
    except Exception as exc:
        logger.debug("youtube handler not loaded: %s", exc)

    try:
        from core.ingest.handlers.github_handler import GitHubHandler
        queue.register_handler("github", _make_handler(GitHubHandler))
    except Exception as exc:
        logger.debug("github handler not loaded: %s", exc)

    try:
        from core.ingest.handlers.pdf_handler import PDFHandler
        queue.register_handler("pdf", _make_handler(PDFHandler))
    except Exception as exc:
        logger.debug("pdf handler not loaded: %s", exc)

    try:
        from core.ingest.handlers.archive_handler import ArchiveHandler
        queue.register_handler("archive", _make_handler(ArchiveHandler))
    except Exception as exc:
        logger.debug("archive handler not loaded: %s", exc)

    try:
        from core.ingest.handlers.audio_handler import AudioHandler
        queue.register_handler("audio", _make_handler(AudioHandler))
        queue.register_handler("video", _make_handler(AudioHandler))
    except Exception as exc:
        logger.debug("audio handler not loaded: %s", exc)

    try:
        from core.ingest.handlers.vision_handler import VisionHandler
        queue.register_handler("image", _make_handler(VisionHandler))
    except Exception as exc:
        logger.debug("vision handler not loaded: %s", exc)

    try:
        from core.ingest.handlers.web_handler import WebHandler
        queue.register_handler("url", _make_handler(WebHandler))
        queue.register_handler("wikipedia", _make_handler(WebHandler))
        queue.register_handler("twitter", _make_handler(WebHandler))
        queue.register_handler("reddit", _make_handler(WebHandler))
        queue.register_handler("instagram", _make_handler(WebHandler))
        queue.register_handler("arxiv", _make_handler(WebHandler))
    except Exception as exc:
        logger.debug("web handler not loaded: %s", exc)

    try:
        from core.ingest.handlers.text_handler import TextHandler
        queue.register_handler("text", _make_handler(TextHandler))
        queue.register_handler("code", _make_handler(TextHandler))
        queue.register_handler("html", _make_handler(TextHandler))
        queue.register_handler("json", _make_handler(TextHandler))
        queue.register_handler("epub", _make_handler(TextHandler))
        queue.register_handler("docx", _make_handler(TextHandler))
        queue.register_handler("spreadsheet", _make_handler(TextHandler))
    except Exception as exc:
        logger.debug("text handler not loaded: %s", exc)

    logger.info("Ingest handlers registered")
