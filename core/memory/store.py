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

from core.memory.models import Base, Task, Event, Reflection, ConversationTurn, Folder, ChatSession, UploadedFile

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

    # ── Folders ─────────────────────────────────────────────────────────────

    async def create_folder(self, name: str) -> Folder:
        folder = Folder(name=name)
        async with self._sf() as session:
            session.add(folder)
            await session.commit()
            await session.refresh(folder)
        return folder

    async def list_folders(self) -> list[Folder]:
        async with self._sf() as session:
            result = await session.execute(select(Folder).order_by(Folder.name))
            return list(result.scalars().all())

    async def rename_folder(self, folder_id: str, name: str) -> Folder | None:
        async with self._sf() as session:
            folder = await session.get(Folder, folder_id)
            if folder is None:
                return None
            folder.name = name
            await session.commit()
            await session.refresh(folder)
        return folder

    async def delete_folder(self, folder_id: str) -> bool:
        """Delete folder and unassign its sessions (sessions are kept)."""
        async with self._sf() as session:
            # Unassign sessions from this folder
            stmt = select(ChatSession).where(ChatSession.folder_id == folder_id)
            result = await session.execute(stmt)
            for s in result.scalars().all():
                s.folder_id = None
            folder = await session.get(Folder, folder_id)
            if folder is None:
                return False
            await session.delete(folder)
            await session.commit()
        return True

    # ── Chat Sessions ────────────────────────────────────────────────────────

    async def create_session(self, title: str = "New chat", folder_id: str | None = None) -> ChatSession:
        s = ChatSession(title=title, folder_id=folder_id)
        async with self._sf() as session:
            session.add(s)
            await session.commit()
            await session.refresh(s)
        return s

    async def list_sessions(self, folder_id: str | None = None, limit: int = 100) -> list[ChatSession]:
        async with self._sf() as session:
            stmt = select(ChatSession).order_by(desc(ChatSession.updated_at)).limit(limit)
            if folder_id is not None:
                stmt = stmt.where(ChatSession.folder_id == folder_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_session(self, session_id: str) -> ChatSession | None:
        async with self._sf() as session:
            return await session.get(ChatSession, session_id)

    async def update_session(
        self,
        session_id: str,
        title: str | None = None,
        folder_id: str | None = None,
        clear_folder: bool = False,
    ) -> ChatSession | None:
        async with self._sf() as session:
            s = await session.get(ChatSession, session_id)
            if s is None:
                return None
            if title is not None:
                s.title = title
            if clear_folder:
                s.folder_id = None
            elif folder_id is not None:
                s.folder_id = folder_id
            await session.commit()
            await session.refresh(s)
        return s

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its conversation turns."""
        async with self._sf() as session:
            # Delete turns
            stmt = select(ConversationTurn).where(ConversationTurn.session_id == session_id)
            result = await session.execute(stmt)
            for turn in result.scalars().all():
                await session.delete(turn)
            s = await session.get(ChatSession, session_id)
            if s is None:
                return False
            await session.delete(s)
            await session.commit()
        return True

    async def list_turns_by_session(self, session_id: str, limit: int = 200) -> list[ConversationTurn]:
        """Chronological turns for a session (oldest first for display)."""
        async with self._sf() as session:
            stmt = (
                select(ConversationTurn)
                .where(ConversationTurn.session_id == session_id)
                .order_by(ConversationTurn.created_at)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_last_turn(self, session_id: str) -> ConversationTurn | None:
        """Get the most recent turn in a session (for sidebar preview)."""
        async with self._sf() as session:
            stmt = (
                select(ConversationTurn)
                .where(ConversationTurn.session_id == session_id)
                .order_by(desc(ConversationTurn.created_at))
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    # ── Uploaded Files ───────────────────────────────────────────────────────

    async def save_file(
        self,
        filename: str,
        content_type: str,
        size: int,
        extracted_text: str | None,
        session_id: str | None = None,
        needs_vision: bool = False,
    ) -> UploadedFile:
        f = UploadedFile(
            filename=filename,
            content_type=content_type,
            size=size,
            extracted_text=extracted_text,
            session_id=session_id,
            needs_vision=needs_vision,
        )
        async with self._sf() as session:
            session.add(f)
            await session.commit()
            await session.refresh(f)
        return f

    # ── Events (extended) ────────────────────────────────────────────────────

    async def list_events(
        self,
        severity: str | None = None,
        limit: int = 50,
    ) -> list[Event]:
        """List events, optionally filtered by severity."""
        async with self._sf() as session:
            stmt = select(Event).order_by(desc(Event.created_at)).limit(limit)
            if severity:
                stmt = stmt.where(Event.severity == severity)
            result = await session.execute(stmt)
            return list(result.scalars().all())


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
