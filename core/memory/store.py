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

from core.memory.models import (
    Base, Task, Event, Reflection, ConversationTurn,
    Folder, ChatSession, UploadedFile,
    KnowledgeNode, KnowledgeEdge, Skill, SkillProgress,
    ResponseQuality, Project, ProjectTask, HabitEvent, ProactiveSubscription,
)

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


    # ── Knowledge Graph ──────────────────────────────────────────────────────

    async def create_node(
        self,
        title: str,
        type: str = "insight",
        summary: str | None = None,
        source_type: str = "manual",
        source_id: str | None = None,
    ) -> KnowledgeNode:
        node = KnowledgeNode(
            title=title,
            type=type,
            summary=summary,
            source_type=source_type,
            source_id=source_id,
        )
        async with self._sf() as session:
            session.add(node)
            await session.commit()
            await session.refresh(node)
        return node

    async def get_node(self, node_id: str) -> KnowledgeNode | None:
        async with self._sf() as session:
            return await session.get(KnowledgeNode, node_id)

    async def list_nodes(
        self,
        type: str | None = None,
        limit: int = 50,
    ) -> list[KnowledgeNode]:
        async with self._sf() as session:
            stmt = select(KnowledgeNode).order_by(desc(KnowledgeNode.created_at)).limit(limit)
            if type:
                stmt = stmt.where(KnowledgeNode.type == type)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def search_nodes(self, query: str, limit: int = 20) -> list[KnowledgeNode]:
        """Fulltext LIKE search across title and summary."""
        from sqlalchemy import or_
        pattern = f"%{query}%"
        async with self._sf() as session:
            stmt = (
                select(KnowledgeNode)
                .where(or_(
                    KnowledgeNode.title.like(pattern),
                    KnowledgeNode.summary.like(pattern),
                ))
                .order_by(desc(KnowledgeNode.created_at))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def create_edge(
        self,
        from_node_id: str,
        to_node_id: str,
        relation_type: str = "related_to",
        weight: float = 1.0,
    ) -> KnowledgeEdge:
        edge = KnowledgeEdge(
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            relation_type=relation_type,
            weight=weight,
        )
        async with self._sf() as session:
            session.add(edge)
            await session.commit()
            await session.refresh(edge)
        return edge

    async def list_edges(
        self,
        node_id: str | None = None,
        limit: int = 100,
    ) -> list[KnowledgeEdge]:
        """List edges, optionally filtered to those touching a given node."""
        from sqlalchemy import or_
        async with self._sf() as session:
            stmt = select(KnowledgeEdge).order_by(desc(KnowledgeEdge.created_at)).limit(limit)
            if node_id:
                stmt = stmt.where(or_(
                    KnowledgeEdge.from_node_id == node_id,
                    KnowledgeEdge.to_node_id == node_id,
                ))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ── Skills ───────────────────────────────────────────────────────────────

    async def create_skill(self, name: str, description: str | None = None) -> Skill:
        skill = Skill(name=name, description=description)
        async with self._sf() as session:
            session.add(skill)
            await session.commit()
            await session.refresh(skill)
        return skill

    async def list_skills(self) -> list[Skill]:
        async with self._sf() as session:
            result = await session.execute(select(Skill).order_by(Skill.name))
            return list(result.scalars().all())

    async def get_skill_by_name(self, name: str) -> Skill | None:
        async with self._sf() as session:
            result = await session.execute(select(Skill).where(Skill.name == name))
            return result.scalars().first()

    async def save_skill_progress(
        self,
        skill_id: str,
        level: float,
        goal: float = 5.0,
        notes: str | None = None,
        assessed_by: str = "auto",
    ) -> SkillProgress:
        sp = SkillProgress(
            skill_id=skill_id,
            level=level,
            goal=goal,
            notes=notes,
            assessed_by=assessed_by,
        )
        async with self._sf() as session:
            session.add(sp)
            await session.commit()
            await session.refresh(sp)
        return sp

    async def get_skill_history(self, skill_id: str, limit: int = 20) -> list[SkillProgress]:
        async with self._sf() as session:
            stmt = (
                select(SkillProgress)
                .where(SkillProgress.skill_id == skill_id)
                .order_by(desc(SkillProgress.assessed_at))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_latest_skill_progress(self, skill_id: str) -> SkillProgress | None:
        history = await self.get_skill_history(skill_id, limit=1)
        return history[0] if history else None

    # ── v4: ResponseQuality ───────────────────────────────────────────────────

    async def save_quality(
        self,
        session_id: str,
        message: str,
        response: str,
        completeness: float,
        accuracy: float,
        helpfulness: float,
        overall: float,
        weak_points: str | None = None,
        improvement_hint: str | None = None,
    ) -> ResponseQuality:
        async with self._sf() as session:
            rq = ResponseQuality(
                session_id=session_id,
                message=message[:2000],
                response=response[:4000],
                completeness=completeness,
                accuracy=accuracy,
                helpfulness=helpfulness,
                overall=overall,
                weak_points=weak_points,
                improvement_hint=improvement_hint,
            )
            session.add(rq)
            await session.commit()
            await session.refresh(rq)
            return rq

    async def list_quality(
        self,
        session_id: str | None = None,
        min_overall: float | None = None,
        limit: int = 50,
    ) -> list[ResponseQuality]:
        async with self._sf() as session:
            stmt = select(ResponseQuality).order_by(desc(ResponseQuality.assessed_at))
            if session_id:
                stmt = stmt.where(ResponseQuality.session_id == session_id)
            if min_overall is not None:
                stmt = stmt.where(ResponseQuality.overall >= min_overall)
            stmt = stmt.limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_quality_stats(self) -> dict:
        """Return average scores and top weak_points from the last 200 assessments."""
        import json
        records = await self.list_quality(limit=200)
        if not records:
            return {
                "count": 0,
                "completeness_avg": 0.0,
                "accuracy_avg": 0.0,
                "helpfulness_avg": 0.0,
                "overall_avg": 0.0,
                "top_weak_points": [],
            }
        n = len(records)
        wp_counts: dict[str, int] = {}
        for r in records:
            if r.weak_points:
                try:
                    for wp in json.loads(r.weak_points):
                        wp_counts[wp] = wp_counts.get(wp, 0) + 1
                except Exception:
                    pass
        top_wp = sorted(wp_counts.items(), key=lambda x: -x[1])[:5]
        return {
            "count": n,
            "completeness_avg": round(sum(r.completeness for r in records) / n, 2),
            "accuracy_avg": round(sum(r.accuracy for r in records) / n, 2),
            "helpfulness_avg": round(sum(r.helpfulness for r in records) / n, 2),
            "overall_avg": round(sum(r.overall for r in records) / n, 2),
            "top_weak_points": [{"point": k, "count": v} for k, v in top_wp],
        }

    async def get_weak_responses(self, min_overall: float = 5.0, limit: int = 20) -> list[ResponseQuality]:
        return await self.list_quality(min_overall=None, limit=limit * 3)

    # ── v4: Projects ──────────────────────────────────────────────────────────

    async def create_project(self, name: str, goal: str | None = None, deadline=None) -> Project:
        async with self._sf() as session:
            p = Project(name=name, goal=goal, deadline=deadline)
            session.add(p)
            await session.commit()
            await session.refresh(p)
            return p

    async def list_projects(self, status: str | None = None) -> list[Project]:
        async with self._sf() as session:
            stmt = select(Project).order_by(desc(Project.created_at))
            if status:
                stmt = stmt.where(Project.status == status)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_project(self, project_id: str) -> Project | None:
        async with self._sf() as session:
            result = await session.execute(select(Project).where(Project.id == project_id))
            return result.scalar_one_or_none()

    async def update_project(self, project_id: str, **kwargs) -> Project | None:
        async with self._sf() as session:
            result = await session.execute(select(Project).where(Project.id == project_id))
            p = result.scalar_one_or_none()
            if p:
                for k, v in kwargs.items():
                    setattr(p, k, v)
                await session.commit()
                await session.refresh(p)
            return p

    async def create_project_task(
        self, project_id: str, description: str, priority: int = 2
    ) -> ProjectTask:
        async with self._sf() as session:
            t = ProjectTask(project_id=project_id, description=description, priority=priority)
            session.add(t)
            await session.commit()
            await session.refresh(t)
            return t

    async def list_project_tasks(self, project_id: str) -> list[ProjectTask]:
        async with self._sf() as session:
            stmt = (
                select(ProjectTask)
                .where(ProjectTask.project_id == project_id)
                .order_by(ProjectTask.priority, ProjectTask.created_at)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_project_task(self, task_id: str, **kwargs) -> ProjectTask | None:
        async with self._sf() as session:
            result = await session.execute(select(ProjectTask).where(ProjectTask.id == task_id))
            t = result.scalar_one_or_none()
            if t:
                for k, v in kwargs.items():
                    setattr(t, k, v)
                await session.commit()
                await session.refresh(t)
            return t

    # ── v4: HabitEvents ───────────────────────────────────────────────────────

    async def record_habit_event(
        self, task_type: str, model_used: str = "", session_id: str | None = None
    ) -> HabitEvent:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        async with self._sf() as session:
            ev = HabitEvent(
                hour_of_day=now.hour,
                day_of_week=now.weekday(),
                task_type=task_type,
                model_used=model_used,
                session_id=session_id,
            )
            session.add(ev)
            await session.commit()
            await session.refresh(ev)
            return ev

    async def get_habit_events(self, limit: int = 500) -> list[HabitEvent]:
        async with self._sf() as session:
            stmt = select(HabitEvent).order_by(desc(HabitEvent.created_at)).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ── v4: ProactiveSubscriptions ────────────────────────────────────────────

    async def create_subscription(
        self, name: str, source_type: str, source_url: str | None = None, keywords: str | None = None
    ) -> ProactiveSubscription:
        async with self._sf() as session:
            sub = ProactiveSubscription(
                name=name, source_type=source_type, source_url=source_url, keywords=keywords
            )
            session.add(sub)
            await session.commit()
            await session.refresh(sub)
            return sub

    async def list_subscriptions(self, enabled_only: bool = True) -> list[ProactiveSubscription]:
        async with self._sf() as session:
            stmt = select(ProactiveSubscription).order_by(ProactiveSubscription.name)
            if enabled_only:
                stmt = stmt.where(ProactiveSubscription.enabled == True)  # noqa: E712
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def touch_subscription(self, sub_id: str) -> None:
        """Update last_checked timestamp."""
        from datetime import datetime, timezone
        async with self._sf() as session:
            result = await session.execute(
                select(ProactiveSubscription).where(ProactiveSubscription.id == sub_id)
            )
            sub = result.scalar_one_or_none()
            if sub:
                sub.last_checked = datetime.now(timezone.utc)
                await session.commit()


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
