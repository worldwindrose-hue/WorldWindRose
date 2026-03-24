"""
ROSA OS — Project Manager.

Manages Projects and ProjectTasks (stored in DB).
Projects group related tasks with goals, deadlines, and status tracking.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.projects.manager")


class ProjectManager:
    """
    High-level API for creating, updating, and querying projects + tasks.
    Delegates storage to core.memory.store.
    """

    async def create_project(
        self,
        name: str,
        goal: str = "",
        deadline: str | None = None,
    ) -> dict[str, Any]:
        """Create a new project."""
        from core.memory.store import get_store
        store = await get_store()
        project = await store.create_project(
            name=name,
            goal=goal,
            deadline=deadline,
        )
        logger.info("Created project: %s (%s)", name, project.id)
        return _project_to_dict(project)

    async def list_projects(self, status: str | None = None) -> list[dict[str, Any]]:
        """List all projects, optionally filtered by status."""
        from core.memory.store import get_store
        store = await get_store()
        projects = await store.list_projects(status=status)
        return [_project_to_dict(p) for p in projects]

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        """Get a project by ID with its tasks."""
        from core.memory.store import get_store
        store = await get_store()
        project = await store.get_project(project_id)
        if not project:
            return None
        tasks = await store.list_project_tasks(project_id=project_id)
        result = _project_to_dict(project)
        result["tasks"] = [_task_to_dict(t) for t in tasks]
        result["progress"] = _calculate_progress(tasks)
        return result

    async def update_project(
        self,
        project_id: str,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        """Update project fields (status, goal, deadline)."""
        from core.memory.store import get_store
        store = await get_store()
        project = await store.update_project(project_id, **kwargs)
        if not project:
            return None
        return _project_to_dict(project)

    async def add_task(
        self,
        project_id: str,
        description: str,
        priority: int = 2,
    ) -> dict[str, Any]:
        """Add a task to a project."""
        from core.memory.store import get_store
        store = await get_store()
        task = await store.create_project_task(
            project_id=project_id,
            description=description,
            priority=priority,
        )
        logger.info("Added task to project %s: %s", project_id, description[:50])
        return _task_to_dict(task)

    async def complete_task(self, task_id: str) -> dict[str, Any] | None:
        """Mark a task as done."""
        from core.memory.store import get_store
        store = await get_store()
        task = await store.update_project_task(task_id, done=True)
        return _task_to_dict(task) if task else None

    async def list_tasks(
        self,
        project_id: str,
        done: bool | None = None,
    ) -> list[dict[str, Any]]:
        """List tasks for a project."""
        from core.memory.store import get_store
        store = await get_store()
        tasks = await store.list_project_tasks(project_id=project_id, done=done)
        return [_task_to_dict(t) for t in tasks]

    async def get_summary(self) -> dict[str, Any]:
        """Return project portfolio summary."""
        all_projects = await self.list_projects()
        total = len(all_projects)
        by_status: dict[str, int] = {}
        for p in all_projects:
            s = p.get("status", "active")
            by_status[s] = by_status.get(s, 0) + 1

        return {
            "total_projects": total,
            "by_status": by_status,
            "active": by_status.get("active", 0),
            "completed": by_status.get("completed", 0),
        }


def _project_to_dict(p: Any) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "goal": getattr(p, "goal", ""),
        "status": getattr(p, "status", "active"),
        "deadline": getattr(p, "deadline", None),
        "created_at": p.created_at.isoformat() if hasattr(p, "created_at") and p.created_at else None,
    }


def _task_to_dict(t: Any) -> dict[str, Any]:
    return {
        "id": t.id,
        "project_id": getattr(t, "project_id", ""),
        "description": t.description,
        "priority": getattr(t, "priority", 2),
        "done": getattr(t, "done", False),
        "created_at": t.created_at.isoformat() if hasattr(t, "created_at") and t.created_at else None,
    }


def _calculate_progress(tasks: list[Any]) -> float:
    if not tasks:
        return 0.0
    done = sum(1 for t in tasks if getattr(t, "done", False))
    return round(done / len(tasks) * 100, 1)


# Singleton
_manager: ProjectManager | None = None


def get_project_manager() -> ProjectManager:
    global _manager
    if _manager is None:
        _manager = ProjectManager()
    return _manager
