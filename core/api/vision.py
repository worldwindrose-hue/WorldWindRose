"""
ROSA OS — Vision API.
Screenshot capture, PDF ingestion, camera.
"""

from __future__ import annotations

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

router = APIRouter(prefix="/api/vision", tags=["vision"])


class ScreenshotAnalyzeRequest(BaseModel):
    prompt: str = "Describe what you see on the screen."


class PDFIngestRequest(BaseModel):
    path: str
    session_id: str = "pdf"


@router.post("/screenshot/capture", response_model=dict)
async def capture_screenshot() -> dict:
    """Capture the current screen and return base64 PNG."""
    from core.integrations.vision.screenshot import capture_screen
    return capture_screen()


@router.post("/screenshot/analyze", response_model=dict)
async def analyze_screenshot(req: ScreenshotAnalyzeRequest) -> dict:
    """Capture screen and analyze with vision model."""
    from core.integrations.vision.screenshot import analyze_screenshot
    return await analyze_screenshot(req.prompt)


@router.get("/camera/status", response_model=dict)
async def camera_status() -> dict:
    """Check camera availability."""
    from core.integrations.vision.camera import is_available, list_cameras
    return {"available": is_available(), "cameras": list_cameras()}


@router.post("/pdf/ingest", response_model=dict)
async def ingest_pdf(req: PDFIngestRequest) -> dict:
    """Ingest a PDF file into the knowledge graph."""
    from core.integrations.vision.pdf_reader import ingest_pdf_to_graph
    return await ingest_pdf_to_graph(req.path, session_id=req.session_id)


@router.get("/health", response_model=dict)
async def vision_health() -> dict:
    """Check health of all vision components."""
    from core.healing.self_healer import full_health_check
    health = await full_health_check()
    return health
