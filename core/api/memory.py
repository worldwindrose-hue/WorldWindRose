"""
ROSA OS — Memory API.
GET  /api/memory/reflections  — list reflections
GET  /api/memory/turns        — list conversation turns
POST /api/memory/events       — store an event
"""

from __future__ import annotations

import logging
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.memory")
router = APIRouter(prefix="/api/memory", tags=["memory"])


class ReflectionOut(BaseModel):
    id: str
    content: str
    suggestions: str | None
    applied: bool
    created_at: str


class TurnOut(BaseModel):
    id: str
    role: str
    content: str
    model_used: str | None
    session_id: str | None
    created_at: str


class EventIn(BaseModel):
    event_type: str           # e.g. "error", "security_alert", "user_feedback"
    description: str
    severity: str = "info"   # "info" | "warning" | "high" | "critical"
    task_id: str | None = None


@router.get("/reflections", response_model=list[ReflectionOut])
async def list_reflections(limit: int = 20) -> list[ReflectionOut]:
    from core.memory.store import get_store
    store = await get_store()
    rows = await store.get_recent_reflections(limit=limit)
    return [
        ReflectionOut(
            id=str(r.id),
            content=r.content,
            suggestions=r.suggestions,
            applied=r.applied,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/turns", response_model=list[TurnOut])
async def list_turns(session_id: str | None = None, limit: int = 50) -> list[TurnOut]:
    from core.memory.store import get_store
    store = await get_store()
    rows = await store.list_turns(session_id=session_id, limit=limit)
    return [
        TurnOut(
            id=str(t.id),
            role=t.role,
            content=t.content,
            model_used=t.model_used,
            session_id=t.session_id,
            created_at=t.created_at.isoformat(),
        )
        for t in rows
    ]


@router.post("/events", status_code=201)
async def store_event(body: EventIn) -> dict:
    from core.memory.store import get_store
    store = await get_store()
    event = await store.save_event(
        event_type=body.event_type,
        description=body.description,
        severity=body.severity,
        task_id=body.task_id,
    )
    return {"id": str(event.id), "status": "stored"}
