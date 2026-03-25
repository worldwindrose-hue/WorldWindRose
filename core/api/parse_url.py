"""
ROSA OS — URL Parsing API
POST /api/parse-url         — fetch a URL and return cleaned text content
POST /api/smart-parse       — autonomous smart parsing with swarm agents (SSE stream)
GET  /api/smart-parse/status — get current parse status
POST /api/solve-problem     — autonomous problem solver
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.parse_url")
router = APIRouter(prefix="/api", tags=["tools"])


class ParseUrlRequest(BaseModel):
    url: str


class SmartParseRequest(BaseModel):
    url: str
    context: str = ""
    stream: bool = True  # True = SSE stream, False = wait for result


class SolveProblemRequest(BaseModel):
    problem: str
    context: dict = {}
    original_task: str = ""


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

    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from tools import WebSearchTool

        tool = WebSearchTool()

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


@router.post("/smart-parse")
async def smart_parse_endpoint(body: SmartParseRequest):
    """
    Autonomous smart parsing with swarm agents.
    If stream=True: returns SSE stream with status updates.
    If stream=False: waits and returns JSON result.
    """
    from core.agents.smart_parser import smart_parse, detect_platform
    from core.status.tracker import set_status, RosaStatus

    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    set_status(RosaStatus.SWARMING, f"🔍 Умный парсинг: {url[:50]}", agents=3)

    if body.stream:
        async def sse_generator():
            status_messages = []

            def cb(msg: str):
                status_messages.append(msg)
                # Also broadcast to Rosa status tracker
                set_status(RosaStatus.SWARMING, msg[:100], agents=3)

            task = asyncio.create_task(smart_parse(url, body.context, status_cb=cb))

            while not task.done():
                while status_messages:
                    msg = status_messages.pop(0)
                    yield f"data: {json.dumps({'type': 'status', 'message': msg})}\n\n"
                await asyncio.sleep(0.15)

            result = await task
            while status_messages:
                yield f"data: {json.dumps({'type': 'status', 'message': status_messages.pop(0)})}\n\n"

            from dataclasses import asdict
            yield f"data: {json.dumps({'type': 'result', 'data': asdict(result)})}\n\n"
            yield "data: [DONE]\n\n"

            set_status(
                RosaStatus.ONLINE if result.success else RosaStatus.ONLINE,
                "✅ Парсинг завершён" if result.success else "⚠️ Парсинг не удался"
            )

        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    else:
        # Non-streaming: wait for result
        messages = []
        result = await smart_parse(url, body.context, status_cb=lambda m: messages.append(m))
        from dataclasses import asdict
        set_status(RosaStatus.ONLINE, "✅ Готова к работе")
        return {
            "success": result.success,
            "url": result.url,
            "platform": result.platform.value,
            "content": result.content,
            "media_path": result.media_path,
            "explanation": result.explanation,
            "alternatives": result.alternatives,
            "attempts": len(result.attempts),
            "duration_ms": result.total_duration_ms,
            "status_log": messages,
        }


@router.post("/solve-problem")
async def solve_problem_endpoint(body: SolveProblemRequest):
    """Autonomous problem solver — never gives up without trying."""
    from core.prediction.proactive import solve_problem
    from core.status.tracker import set_status, RosaStatus

    messages = []

    def cb(msg: str):
        messages.append(msg)
        set_status(RosaStatus.INFERRING, msg[:100])

    set_status(RosaStatus.INFERRING, f"🔍 Решаю: {body.problem[:60]}")
    result = await solve_problem(
        body.problem, body.context, body.original_task, status_cb=cb
    )
    set_status(RosaStatus.ONLINE, "✅ Готова к работе")

    from dataclasses import asdict
    return {**asdict(result), "status_log": messages}
