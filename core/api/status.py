"""
ROSA OS — Status API.

GET /api/status/current    → current Rosa status
GET /api/status/history    → last N status events
WS  /api/ws/status         → live status updates
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.status.tracker import get_tracker, STATUS_COLOR

logger = logging.getLogger("rosa.api.status")
router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status/current")
async def get_current_status():
    tracker = get_tracker()
    evt = tracker.get_current()
    d = evt.to_dict()
    d["color"] = STATUS_COLOR.get(evt.status, "gray")  # type: ignore[arg-type]
    return d


@router.get("/status/history")
async def get_status_history(limit: int = 50):
    tracker = get_tracker()
    events = await tracker.get_history(limit=limit)
    return [e.to_dict() for e in events]


@router.websocket("/ws/status")
async def ws_status(websocket: WebSocket) -> None:
    """Stream live status events to the client."""
    await websocket.accept()
    tracker = get_tracker()
    q = tracker.subscribe()

    # Send current status immediately
    current = tracker.get_current().to_dict()
    current["color"] = STATUS_COLOR.get(tracker.get_current().status, "gray")  # type: ignore[arg-type]
    await websocket.send_json(current)

    try:
        while True:
            try:
                import asyncio
                payload = await asyncio.wait_for(q.get(), timeout=30.0)
                payload["color"] = STATUS_COLOR.get(payload.get("status", ""), "gray")
                await websocket.send_json(payload)
            except asyncio.TimeoutError:
                # Keepalive ping
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("Status WS error: %s", exc)
    finally:
        tracker.unsubscribe(q)
