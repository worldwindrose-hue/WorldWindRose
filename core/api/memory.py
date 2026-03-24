"""
ROSA OS — Memory API.
GET  /api/memory/reflections  — list reflections
GET  /api/memory/turns        — list conversation turns
POST /api/memory/events       — store an event
GET  /api/memory/search       — search episodic+graph
GET  /api/memory/graph        — graph around entity
POST /api/memory/remember     — add to all layers
DELETE /api/memory/forget/{id} — remove from episodic
GET  /api/memory/context      — session context
GET  /api/memory/stats        — memory counts
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


class RememberIn(BaseModel):
    text: str
    importance: float = 0.5


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


@router.get("/search")
async def search_memory(q: str = "", limit: int = 10) -> dict:
    """Search episodic and graph memory."""
    if not q:
        return {"episodic": [], "graph": []}
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        episodic = await mem.episodic.search(q, top_k=limit)
        graph = await mem.graph.query(q)
        return {"episodic": episodic, "graph": graph}
    except Exception as exc:
        logger.warning("Memory search failed: %s", exc)
        return {"episodic": [], "graph": [], "error": str(exc)}


@router.get("/graph")
async def get_graph(entity: str = "") -> dict:
    """Get graph around a given entity."""
    if not entity:
        return {"nodes": [], "edges": []}
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        results = await mem.graph.query(entity)
        return {"entity": entity, "relations": results}
    except Exception as exc:
        logger.warning("Graph query failed: %s", exc)
        return {"entity": entity, "relations": [], "error": str(exc)}


@router.post("/remember", status_code=201)
async def remember(body: RememberIn) -> dict:
    """Add text to all memory layers."""
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        await mem.remember("user", body.text, source="api", importance=body.importance)
        return {"status": "remembered", "importance": body.importance}
    except Exception as exc:
        logger.warning("Remember failed: %s", exc)
        return {"status": "error", "error": str(exc)}


@router.delete("/forget/{entry_id}")
async def forget(entry_id: str) -> dict:
    """Remove an entry from episodic memory."""
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        ok = await mem.episodic.delete(entry_id)
        return {"status": "deleted" if ok else "not_found", "id": entry_id}
    except Exception as exc:
        logger.warning("Forget failed: %s", exc)
        return {"status": "error", "error": str(exc)}


@router.get("/context")
async def get_context() -> dict:
    """Get current session context."""
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        ctx = await mem.context.load()
        return {"context": ctx}
    except Exception as exc:
        logger.warning("Context load failed: %s", exc)
        return {"context": {}, "error": str(exc)}


@router.get("/stats")
async def memory_stats() -> dict:
    """Get memory statistics."""
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        stats = await mem.stats()
        return stats
    except Exception as exc:
        logger.warning("Memory stats failed: %s", exc)
        return {"error": str(exc)}
