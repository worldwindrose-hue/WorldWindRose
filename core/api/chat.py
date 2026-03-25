"""
ROSA OS — Chat API endpoints.
POST /api/chat        — single-turn chat
WS   /api/ws/chat     — streaming WebSocket chat
"""

from __future__ import annotations

import asyncio
import json
import uuid
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.router import get_router

logger = logging.getLogger("rosa.api.chat")
router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    mode: str | None = None      # "cloud" | "local" | None (auto)
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    brain_used: str
    model: str
    task_type: str
    confidence: float
    session_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Single-turn chat with Rosa."""
    session_id = req.session_id or str(uuid.uuid4())
    rosa = get_router()

    try:
        result = await asyncio.wait_for(
            rosa.chat(
                message=req.message,
                force_mode=req.mode,
                session_id=session_id,
            ),
            timeout=115.0,
        )
    except asyncio.TimeoutError:
        return ChatResponse(
            response="⏱️ Запрос занял слишком много времени. Попробуй сократить вопрос или используй Local Brain.",
            brain_used="timeout",
            model="none",
            task_type="timeout",
            confidence=0.0,
            session_id=session_id,
        )

    # Persist to memory asynchronously (best-effort)
    try:
        from core.memory.store import get_store
        store = await get_store()
        await store.save_turn(
            role="user",
            content=req.message,
            session_id=session_id,
        )
        await store.save_turn(
            role="assistant",
            content=result["response"],
            model_used=result["model"],
            session_id=session_id,
        )
    except Exception as exc:
        logger.warning("Memory persistence failed: %s", exc)

    # Eternal memory: remember user message and response (fire-and-forget)
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        asyncio.create_task(mem.remember("user", req.message, source="chat", importance=0.5))
        asyncio.create_task(mem.remember("assistant", result["response"], source="chat", importance=0.4))
    except Exception as exc:
        logger.debug("Eternal memory update skipped: %s", exc)

    return ChatResponse(
        response=result["response"],
        brain_used=result["brain_used"],
        model=result["model"],
        task_type=result["task_type"],
        confidence=result["confidence"],
        session_id=session_id,
    )


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket, session_id: str | None = None) -> None:
    """WebSocket chat endpoint — real-time streaming responses."""
    await websocket.accept()
    # Reuse session_id from query param if supplied by the client
    if not session_id:
        session_id = str(uuid.uuid4())
    rosa = get_router()

    await websocket.send_json({"type": "connected", "session_id": session_id})

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            message = data.get("message", "").strip()
            mode = data.get("mode")

            if not message:
                continue

            await websocket.send_json({"type": "thinking", "session_id": session_id})

            # Update Rosa's status
            try:
                from core.status.tracker import set_status, RosaStatus
                set_status(RosaStatus.THINKING, f"Обрабатываю: {message[:60]}")
            except Exception:
                pass

            try:
                result = await rosa.chat(
                    message=message,
                    force_mode=mode,
                    session_id=session_id,
                )

                await websocket.send_json({
                    "type": "response",
                    "response": result["response"],
                    "brain_used": result["brain_used"],
                    "model": result["model"],
                    "task_type": result["task_type"],
                    "confidence": result["confidence"],
                    "session_id": session_id,
                })

                # Back to online
                try:
                    from core.status.tracker import set_status, RosaStatus
                    set_status(RosaStatus.ONLINE, "Готова к работе")
                except Exception:
                    pass

                # Persist + metacognition (fire-and-forget)
                try:
                    from core.memory.store import get_store
                    store = await get_store()
                    await store.save_turn(role="user", content=message, session_id=session_id)
                    await store.save_turn(
                        role="assistant",
                        content=result["response"],
                        model_used=result["model"],
                        session_id=session_id,
                    )
                except Exception as exc:
                    logger.warning("Memory persistence failed: %s", exc)

                # Metacognitive self-evaluation — runs in background
                try:
                    from core.metacognition.evaluator import evaluate_response
                    asyncio.create_task(
                        evaluate_response(message, result["response"], session_id)
                    )
                except Exception:
                    pass

            except Exception as exc:
                logger.error("Chat error: %s", exc)
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Error processing message: {exc}",
                        "session_id": session_id,
                    })
                except Exception:
                    pass  # connection already closed, nothing to do

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
