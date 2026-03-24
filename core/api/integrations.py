"""
ROSA OS — Unified Integrations API.
Provides endpoints for TikTok, GitHub, Telegram, and PDF ingestion.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.integrations")
router = APIRouter(prefix="/api/integrations", tags=["integrations"])


# ── TikTok ────────────────────────────────────────────────────────────────────

class TikTokRequest(BaseModel):
    url: str


@router.post("/tiktok/analyze", status_code=201)
async def tiktok_analyze(req: TikTokRequest) -> dict[str, Any]:
    """Extract TikTok video metadata and ingest into knowledge graph."""
    try:
        from core.integrations.socials.tiktok import TikTokConnector
        connector = TikTokConnector()
        result = await connector.ingest_to_graph(req.url)
        return result
    except Exception as exc:
        logger.error("TikTok analyze error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── GitHub ────────────────────────────────────────────────────────────────────

class GitHubRequest(BaseModel):
    url: str
    max_files: int = 10


@router.post("/github/ingest", status_code=201)
async def github_ingest(req: GitHubRequest) -> dict[str, Any]:
    """Read a GitHub repository and ingest key files into knowledge graph."""
    if req.max_files < 1 or req.max_files > 50:
        raise HTTPException(status_code=422, detail="max_files must be 1-50")
    try:
        from core.integrations.workspace.github import GitHubConnector
        connector = GitHubConnector()
        result = await connector.ingest_to_graph(req.url, max_files=req.max_files)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("GitHub ingest error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Telegram ─────────────────────────────────────────────────────────────────

class TelegramImportRequest(BaseModel):
    chat_id: str
    limit: int = 100


class TelegramAuthVerifyRequest(BaseModel):
    code: str


@router.post("/telegram/auth/start")
async def telegram_auth_start() -> dict[str, str]:
    """Send OTP to configured Telegram phone number."""
    try:
        from core.integrations.socials.telegram_user import start_auth
        return await start_auth()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/telegram/auth/verify")
async def telegram_auth_verify(req: TelegramAuthVerifyRequest) -> dict[str, str]:
    """Verify OTP and save Telethon session."""
    try:
        from core.integrations.socials.telegram_user import verify_auth
        return await verify_auth(req.code)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/telegram/import", status_code=201)
async def telegram_import(req: TelegramImportRequest) -> dict[str, Any]:
    """Import Telegram chat history into knowledge graph."""
    if req.limit < 1 or req.limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be 1-1000")
    try:
        from core.integrations.socials.telegram_user import import_to_graph
        return await import_to_graph(req.chat_id, req.limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Telegram import error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── PDF ───────────────────────────────────────────────────────────────────────

class PDFIngestRequest(BaseModel):
    file_path: str       # absolute or relative path on the server
    max_pages: int = 50


@router.post("/pdf/ingest", status_code=201)
async def pdf_ingest(req: PDFIngestRequest) -> dict[str, Any]:
    """Extract text from a PDF file and ingest into knowledge graph."""
    try:
        from core.integrations.vision.pdf_reader import ingest_pdf
        return await ingest_pdf(req.file_path, max_pages=req.max_pages)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found: {req.file_path}")
    except Exception as exc:
        logger.error("PDF ingest error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
async def integrations_status() -> dict[str, Any]:
    """Return configuration status of all connectors."""
    import os
    return {
        "tiktok": {"configured": True, "note": "No credentials required for public videos"},
        "github": {
            "configured": bool(os.getenv("GITHUB_TOKEN")),
            "note": "GITHUB_TOKEN optional (60 req/h without, 5000 with)",
        },
        "telegram": {
            "configured": all(os.getenv(v) for v in ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_PHONE"]),
            "authenticated": bool(os.getenv("TELEGRAM_SESSION")),
        },
    }
