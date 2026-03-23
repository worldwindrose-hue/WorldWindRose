"""
ROSA OS — Task management API.
GET    /api/tasks           — list tasks
POST   /api/tasks           — create task
PATCH  /api/tasks/{task_id} — update task (status, rating, result)
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.tasks")
router = APIRouter(prefix="/api", tags=["tasks"])


class TaskCreate(BaseModel):
    description: str
    plan: str | None = None


class TaskUpdate(BaseModel):
    status: str | None = None       # "pending" | "in_progress" | "done" | "failed"
    result: str | None = None
    owner_rating: int | None = None  # 1–5
    plan: str | None = None


class TaskOut(BaseModel):
    id: str
    description: str
    plan: str | None
    result: str | None
    status: str
    owner_rating: int | None
    created_at: str
    updated_at: str


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(limit: int = 50, status: str | None = None) -> list[TaskOut]:
    from core.memory.store import get_store
    store = await get_store()
    tasks = await store.list_tasks(limit=limit, status=status)
    return [
        TaskOut(
            id=str(t.id),
            description=t.description,
            plan=t.plan,
            result=t.result,
            status=t.status,
            owner_rating=t.owner_rating,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
        )
        for t in tasks
    ]


@router.post("/tasks", response_model=TaskOut, status_code=201)
async def create_task(body: TaskCreate) -> TaskOut:
    from core.memory.store import get_store
    store = await get_store()
    task = await store.save_task(description=body.description, plan=body.plan)
    return TaskOut(
        id=str(task.id),
        description=task.description,
        plan=task.plan,
        result=task.result,
        status=task.status,
        owner_rating=task.owner_rating,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, body: TaskUpdate) -> TaskOut:
    from core.memory.store import get_store
    store = await get_store()
    task = await store.update_task(
        task_id=task_id,
        status=body.status,
        result=body.result,
        owner_rating=body.owner_rating,
        plan=body.plan,
    )
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOut(
        id=str(task.id),
        description=task.description,
        plan=task.plan,
        result=task.result,
        status=task.status,
        owner_rating=task.owner_rating,
        created_at=task.created_at.isoformat(),
        updated_at=task.updated_at.isoformat(),
    )
