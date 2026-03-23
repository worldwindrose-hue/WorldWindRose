"""
ROSA OS — Async SQLite store for persistent memory.
All operations are async and use SQLAlchemy 2.0 async engine.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, desc, and_

from core.memory.models import Base, Task, Event, Reflection, ConversationTurn

logger = logging.getLogger("rosa.memory.store")

_engine = None
_session_factory = None


async def init_db(db_path: str | None = None) -> None:
    """Initialize the database engine and create all tables."""
    global _engine, _session_factory

    if db_path is None:
        from core.config import get_settings
        db_path = get_settings().db_path

    # Ensure directory exists
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}",
        echo=False,
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Database initialized at %s", db_path)


class MemoryStore:
    """Async CRUD interface for ROSA OS memory."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._sf = session_factory

    # ── Conversation Turns ──────────────────────────────────────────────────

    async def save_turn(
        self,
        role: str,
        content: str,
        model_used: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
    ) -> ConversationTurn:
        turn = ConversationTurn(
            role=role,
            content=content,
            model_used=model_used,
            session_id=session_id,
            task_id=task_id,
        )
        async with self._sf() as session:
            session.add(turn)
            await session.commit()
            await session.refresh(turn)
        return turn

    async def list_turns(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[ConversationTurn]:
        async with self._sf() as session:
            stmt = select(ConversationTurn).order_by(desc(ConversationTurn.created_at)).limit(limit)
            if session_id:
                stmt = stmt.where(ConversationTurn.session_id == session_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ── Tasks ───────────────────────────────────────────────────────────────

    async def save_task(
        self,
        description: str,
        plan: str | None = None,
        status: str = "pending",
    ) -> Task:
        task = Task(description=description, plan=plan, status=status)
        async with self._sf() as session:
            session.add(task)
            await session.commit()
            await session.refresh(task)
        return task

    async def update_task(
        self,
        task_id: str,
        status: str | None = None,
        result: str | None = None,
        owner_rating: int | None = None,
        plan: str | None = None,
    ) -> Task | None:
        async with self._sf() as session:
            task = await session.get(Task, task_id)
            if task is None:
                return None
            if status is not None:
                task.status = status
            if result is not None:
                task.result = result
            if owner_rating is not None:
                task.owner_rating = owner_rating
            if plan is not None:
                task.plan = plan
            await session.commit()
            await session.refresh(task)
        return task

    async def list_tasks(
        self,
        limit: int = 50,
        status: str | None = None,
    ) -> list[Task]:
        async with self._sf() as session:
            stmt = select(Task).order_by(desc(Task.created_at)).limit(limit)
            if status:
                stmt = stmt.where(Task.status == status)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_failed_tasks(self, limit: int = 50) -> list[Task]:
        return await self.list_tasks(limit=limit, status="failed")

    async def get_low_rated_tasks(self, max_rating: int = 2, limit: int = 50) -> list[Task]:
        async with self._sf() as session:
            stmt = (
                select(Task)
                .where(and_(Task.owner_rating.is_not(None), Task.owner_rating <= max_rating))
                .order_by(desc(Task.created_at))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ── Events ──────────────────────────────────────────────────────────────

    async def save_event(
        self,
        event_type: str,
        description: str,
        severity: str = "info",
        task_id: str | None = None,
    ) -> Event:
        event = Event(
            event_type=event_type,
            description=description,
            severity=severity,
            task_id=task_id,
        )
        async with self._sf() as session:
            session.add(event)
            await session.commit()
            await session.refresh(event)
        return event

    async def get_high_severity_events(self, limit: int = 50) -> list[Event]:
        async with self._sf() as session:
            stmt = (
                select(Event)
                .where(Event.severity.in_(["high", "critical"]))
                .order_by(desc(Event.created_at))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ── Reflections ─────────────────────────────────────────────────────────

    async def save_reflection(
        self,
        content: str,
        suggestions: str | None = None,
    ) -> Reflection:
        reflection = Reflection(content=content, suggestions=suggestions)
        async with self._sf() as session:
            session.add(reflection)
            await session.commit()
            await session.refresh(reflection)
        return reflection

    async def get_recent_reflections(self, limit: int = 20) -> list[Reflection]:
        async with self._sf() as session:
            stmt = select(Reflection).order_by(desc(Reflection.created_at)).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def mark_reflection_applied(self, reflection_id: str) -> Reflection | None:
        async with self._sf() as session:
            reflection = await session.get(Reflection, reflection_id)
            if reflection is None:
                return None
            reflection.applied = True
            await session.commit()
            await session.refresh(reflection)
        return reflection


# Module-level singleton
_store_instance: MemoryStore | None = None


async def get_store() -> MemoryStore:
    """Get or create the singleton MemoryStore."""
    global _store_instance
    if _store_instance is None:
        if _session_factory is None:
            await init_db()
        _store_instance = MemoryStore(_session_factory)
    return _store_instance
