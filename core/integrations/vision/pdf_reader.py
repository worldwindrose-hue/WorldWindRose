"""
ROSA OS — PDF Reader & Knowledge Graph Ingestion.

Reads PDF files via pypdf, chunks content, and ingests into knowledge graph.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.integrations.vision.pdf_reader")

_CHUNK_SIZE = 1000  # characters per chunk
_CHUNK_OVERLAP = 100


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


def read_pdf(path: str | Path) -> dict[str, Any]:
    """
    Read a PDF file and extract text from all pages.

    Returns:
        {"success": bool, "pages": int, "text": str, "chunks": list[str], "title": str}
    """
    try:
        import pypdf
    except ImportError:
        return {
            "success": False,
            "error": "pypdf not installed. Run: pip install pypdf",
            "text": "",
            "chunks": [],
        }

    path = Path(path)
    if not path.exists():
        return {"success": False, "error": f"File not found: {path}", "text": "", "chunks": []}

    try:
        reader = pypdf.PdfReader(str(path))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages_text.append(text)

        full_text = "\n\n".join(pages_text)
        chunks = _chunk_text(full_text)

        # Try to get PDF metadata
        meta = reader.metadata or {}
        title = meta.get("/Title", path.stem) or path.stem

        return {
            "success": True,
            "pages": len(pages_text),
            "text": full_text,
            "chunks": chunks,
            "title": str(title),
            "path": str(path),
            "chunk_count": len(chunks),
        }
    except Exception as exc:
        logger.error("PDF read failed for %s: %s", path, exc)
        return {"success": False, "error": str(exc), "text": "", "chunks": []}


async def ingest_pdf_to_graph(path: str | Path, session_id: str = "pdf") -> dict[str, Any]:
    """
    Read PDF → chunk → add each chunk to knowledge graph.

    Returns:
        {"success": bool, "pages": int, "chunks_processed": int, "nodes_created": int}
    """
    result = read_pdf(path)
    if not result["success"]:
        return {"success": False, "error": result.get("error"), "nodes_created": 0}

    title = result["title"]
    chunks = result["chunks"]
    nodes_created = 0

    try:
        from core.knowledge.graph import add_insight
    except ImportError:
        return {
            "success": False,
            "error": "Knowledge graph not available",
            "nodes_created": 0,
        }

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        try:
            r = await add_insight(
                text=chunk,
                metadata={
                    "source": "pdf",
                    "title": title,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "path": str(path),
                },
                session_id=session_id,
            )
            nodes_created += r.get("nodes_created", 0)
        except Exception as exc:
            logger.debug("Chunk %d ingest failed: %s", i, exc)

    logger.info("PDF %s: %d chunks → %d nodes", title, len(chunks), nodes_created)
    return {
        "success": True,
        "title": title,
        "pages": result["pages"],
        "chunks_processed": len(chunks),
        "nodes_created": nodes_created,
    }


def index_directory(directory: str | Path, extensions: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Scan a directory for PDF files and return metadata index.
    Does not ingest — just enumerates.
    """
    extensions = extensions or [".pdf"]
    directory = Path(directory)
    if not directory.exists():
        return []

    results = []
    for ext in extensions:
        for pdf_path in directory.rglob(f"*{ext}"):
            try:
                stat = pdf_path.stat()
                results.append({
                    "path": str(pdf_path),
                    "name": pdf_path.stem,
                    "size_bytes": stat.st_size,
                    "hash": hashlib.md5(str(pdf_path).encode()).hexdigest()[:8],
                })
            except Exception:
                pass

    return sorted(results, key=lambda x: x["size_bytes"], reverse=True)
