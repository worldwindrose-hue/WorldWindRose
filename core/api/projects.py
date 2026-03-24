"""
ROSA OS — Projects API.
CRUD for Projects and ProjectTasks.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    goal: str = ""
    deadline: str | None = None


class ProjectUpdate(BaseModel):
    status: str | None = None
    goal: str | None = None
    deadline: str | None = None


class TaskCreate(BaseModel):
    description: str
    priority: int = 2


@router.post("", response_model=dict)
async def create_project(req: ProjectCreate) -> dict:
    from core.projects.manager import get_project_manager
    pm = get_project_manager()
    return await pm.create_project(name=req.name, goal=req.goal, deadline=req.deadline)


@router.get("", response_model=list)
async def list_projects(status: str | None = None) -> list:
    from core.projects.manager import get_project_manager
    pm = get_project_manager()
    return await pm.list_projects(status=status)


@router.get("/summary", response_model=dict)
async def project_summary() -> dict:
    from core.projects.manager import get_project_manager
    pm = get_project_manager()
    return await pm.get_summary()


@router.get("/{project_id}", response_model=dict)
async def get_project(project_id: str) -> dict:
    from core.projects.manager import get_project_manager
    pm = get_project_manager()
    project = await pm.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}", response_model=dict)
async def update_project(project_id: str, req: ProjectUpdate) -> dict:
    from core.projects.manager import get_project_manager
    pm = get_project_manager()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    project = await pm.update_project(project_id, **updates)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project_id}/tasks", response_model=dict)
async def add_task(project_id: str, req: TaskCreate) -> dict:
    from core.projects.manager import get_project_manager
    pm = get_project_manager()
    return await pm.add_task(project_id=project_id, description=req.description, priority=req.priority)


@router.get("/{project_id}/tasks", response_model=list)
async def list_tasks(project_id: str, done: bool | None = None) -> list:
    from core.projects.manager import get_project_manager
    pm = get_project_manager()
    return await pm.list_tasks(project_id=project_id, done=done)


@router.patch("/tasks/{task_id}/complete", response_model=dict)
async def complete_task(task_id: str) -> dict:
    from core.projects.manager import get_project_manager
    pm = get_project_manager()
    task = await pm.complete_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
