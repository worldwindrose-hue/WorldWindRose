"""
ROSA OS v2 — File Upload API
POST /api/files/upload  — upload a file, extract text, return {file_id, extracted_text, ...}
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.files")
router = APIRouter(prefix="/api/files", tags=["files"])

UPLOAD_DIR = Path("memory/uploads")
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

TEXT_EXTENSIONS = {".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".csv", ".log", ".html", ".xml"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


class FileUploadOut(BaseModel):
    file_id: str
    filename: str
    content_type: str
    size: int
    extracted_text: str | None
    needs_vision: bool
    message: str


async def _extract_text(path: Path, content_type: str, suffix: str) -> tuple[str | None, bool]:
    """Extract text from a file. Returns (text, needs_vision)."""

    # PDF extraction
    if suffix == ".pdf" or "pdf" in content_type:
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            pages_text = []
            for page in reader.pages[:30]:  # cap at 30 pages
                pages_text.append(page.extract_text() or "")
            text = "\n\n".join(p for p in pages_text if p.strip())
            if not text.strip():
                return "[PDF: no extractable text — may be scanned. Vision analysis planned.]", True
            return text[:20000], False  # cap at 20k chars
        except ImportError:
            return "[PDF: pypdf not installed. Run: pip3 install pypdf]", False
        except Exception as exc:
            logger.error("PDF extraction failed: %s", exc)
            return f"[PDF extraction error: {exc}]", False

    # Plain text / code files
    if suffix in TEXT_EXTENSIONS:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return text[:20000], False
        except Exception as exc:
            return f"[Text read error: {exc}]", False

    # Images
    if suffix in IMAGE_EXTENSIONS or content_type.startswith("image/"):
        return f"[IMAGE: {path.name} — vision analysis will be available when Kimi-vision is configured]", True

    # Audio/video
    if content_type.startswith(("audio/", "video/")):
        return f"[MEDIA: {path.name} — transcription/analysis planned via voice/vision integration]", True

    # Unknown
    return f"[File type '{suffix}' not yet supported for text extraction]", False


@router.post("/upload", response_model=FileUploadOut, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    session_id: str | None = None,
) -> FileUploadOut:
    """Upload a file and extract its text content."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    # Read content
    content = await file.read()
    size = len(content)

    if size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_FILE_SIZE // (1024*1024)} MB)")

    # Save to disk
    from core.memory.store import get_store
    store = await get_store()

    # Generate a unique filename to avoid collisions
    import uuid
    file_id = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{file_id}{suffix}"
    save_path.write_bytes(content)

    # Extract text
    extracted_text, needs_vision = await _extract_text(save_path, content_type, suffix)

    # Persist metadata
    db_file = await store.save_file(
        filename=filename,
        content_type=content_type,
        size=size,
        extracted_text=extracted_text,
        session_id=session_id,
        needs_vision=needs_vision,
    )

    msg = "File uploaded successfully."
    if needs_vision:
        msg += " Vision analysis will be available once Kimi-vision is configured."

    return FileUploadOut(
        file_id=db_file.id,
        filename=filename,
        content_type=content_type,
        size=size,
        extracted_text=extracted_text,
        needs_vision=needs_vision,
        message=msg,
    )
