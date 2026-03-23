"""
ROSA OS v2 — Chat Sessions API
GET    /api/sessions            — list all sessions (with last-message preview)
POST   /api/sessions            — create new session
GET    /api/sessions/{id}       — session + messages
PATCH  /api/sessions/{id}       — rename / move to folder
DELETE /api/sessions/{id}       — delete session + all turns
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.sessions")
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = "New chat"
    folder_id: str | None = None


class SessionUpdate(BaseModel):
    title: str | None = None
    folder_id: str | None = None
    clear_folder: bool = False


class TurnOut(BaseModel):
    id: str
    role: str
    content: str
    model_used: str | None
    created_at: str


class SessionOut(BaseModel):
    id: str
    title: str
    folder_id: str | None
    created_at: str
    updated_at: str
    last_message: str | None = None     # preview for sidebar


class SessionDetail(SessionOut):
    messages: list[TurnOut]


def _group_label(dt: datetime) -> str:
    """Return a display group label for a session's updated_at."""
    now = datetime.now(timezone.utc)
    delta = now - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else now - dt
    if delta < timedelta(hours=24):
        return "Today"
    if delta < timedelta(hours=48):
        return "Yesterday"
    if delta < timedelta(days=7):
        return "This week"
    return "Older"


@router.get("", response_model=list[SessionOut])
async def list_sessions(folder_id: str | None = None, limit: int = 100) -> list[SessionOut]:
    from core.memory.store import get_store
    store = await get_store()
    sessions = await store.list_sessions(folder_id=folder_id, limit=limit)
    result = []
    for s in sessions:
        last_turn = await store.get_last_turn(s.id)
        preview = None
        if last_turn:
            preview = last_turn.content[:80] + ("…" if len(last_turn.content) > 80 else "")
        result.append(SessionOut(
            id=s.id,
            title=s.title,
            folder_id=s.folder_id,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
            last_message=preview,
        ))
    return result


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(body: SessionCreate) -> SessionOut:
    from core.memory.store import get_store
    store = await get_store()
    s = await store.create_session(title=body.title, folder_id=body.folder_id)
    return SessionOut(
        id=s.id,
        title=s.title,
        folder_id=s.folder_id,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str) -> SessionDetail:
    from core.memory.store import get_store
    store = await get_store()
    s = await store.get_session(session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    turns = await store.list_turns_by_session(session_id)
    return SessionDetail(
        id=s.id,
        title=s.title,
        folder_id=s.folder_id,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
        messages=[
            TurnOut(
                id=t.id,
                role=t.role,
                content=t.content,
                model_used=t.model_used,
                created_at=t.created_at.isoformat(),
            )
            for t in turns
        ],
    )


@router.patch("/{session_id}", response_model=SessionOut)
async def update_session(session_id: str, body: SessionUpdate) -> SessionOut:
    from core.memory.store import get_store
    store = await get_store()
    s = await store.update_session(
        session_id,
        title=body.title,
        folder_id=body.folder_id,
        clear_folder=body.clear_folder,
    )
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionOut(
        id=s.id,
        title=s.title,
        folder_id=s.folder_id,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    from core.memory.store import get_store
    store = await get_store()
    ok = await store.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")
