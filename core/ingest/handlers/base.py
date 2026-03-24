"""Base class for all ingest handlers."""

from __future__ import annotations

import logging
import textwrap
from typing import Optional

logger = logging.getLogger("rosa.ingest.handler")

_DEFAULT_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100


class BaseHandler:
    """Base class with common chunking and graph-saving logic."""

    async def process(self, job) -> "IngestResult":
        raise NotImplementedError

    def chunk(self, text: str, size: int = _DEFAULT_CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
        """Split text into overlapping chunks for better retrieval."""
        if not text.strip():
            return []
        words = text.split()
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i : i + size])
            chunks.append(chunk)
            i += size - overlap
        return [c for c in chunks if c.strip()]

    async def save_to_graph(
        self,
        chunks: list[str],
        source: str,
        tags: list[str] = None,
        extra_meta: dict = None,
    ) -> int:
        from core.ingest.universal_ingester import _save_chunks_to_graph
        return await _save_chunks_to_graph(chunks, source, tags or [], extra_meta)

    def update_progress(self, job, pct: int, detail: str = "") -> None:
        from core.ingest.job_queue import get_job_queue
        get_job_queue().update_progress(job.id, pct, detail)


# Re-export result type
from core.ingest.universal_ingester import IngestResult
