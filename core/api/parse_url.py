"""
ROSA OS v2 — URL Parsing API
POST /api/parse-url  — fetch a URL and return cleaned text content
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.parse_url")
router = APIRouter(prefix="/api", tags=["tools"])


class ParseUrlRequest(BaseModel):
    url: str


class ParseUrlOut(BaseModel):
    url: str
    title: str | None
    content: str
    truncated: bool


def _extract_title(html: str) -> str | None:
    """Extract <title> from raw HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()[:200]
    return None


@router.post("/parse-url", response_model=ParseUrlOut)
async def parse_url(body: ParseUrlRequest) -> ParseUrlOut:
    """Fetch a URL and return its cleaned text content for use in chat."""
    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # Reuse WebSearchTool from tools.py
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from tools import WebSearchTool

        tool = WebSearchTool()

        # Fetch raw HTML for title extraction
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={"User-Agent": "ROSA-OS/2.0 (web reader)"},
                )
                resp.raise_for_status()
                raw_html = resp.text
            title = _extract_title(raw_html)
        except Exception:
            raw_html = ""
            title = None

        # Get cleaned text via WebSearchTool
        content = await tool.fetch(url)

        if content.startswith("[Error"):
            raise HTTPException(status_code=422, detail=content)

        truncated = len(content) >= 8000
        return ParseUrlOut(url=url, title=title, content=content, truncated=truncated)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("URL parse failed for %s: %s", url, exc)
        raise HTTPException(status_code=500, detail=f"Failed to parse URL: {exc}")
