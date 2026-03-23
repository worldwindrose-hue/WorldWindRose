"""
ROSA OS v2 — Folders API
GET    /api/folders       — list all folders
POST   /api/folders       — create folder
PATCH  /api/folders/{id}  — rename
DELETE /api/folders/{id}  — delete (sessions are kept, just unassigned)
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/folders", tags=["folders"])


class FolderCreate(BaseModel):
    name: str


class FolderUpdate(BaseModel):
    name: str


class FolderOut(BaseModel):
    id: str
    name: str
    created_at: str


@router.get("", response_model=list[FolderOut])
async def list_folders() -> list[FolderOut]:
    from core.memory.store import get_store
    store = await get_store()
    folders = await store.list_folders()
    return [FolderOut(id=f.id, name=f.name, created_at=f.created_at.isoformat()) for f in folders]


@router.post("", response_model=FolderOut, status_code=201)
async def create_folder(body: FolderCreate) -> FolderOut:
    from core.memory.store import get_store
    store = await get_store()
    f = await store.create_folder(name=body.name)
    return FolderOut(id=f.id, name=f.name, created_at=f.created_at.isoformat())


@router.patch("/{folder_id}", response_model=FolderOut)
async def rename_folder(folder_id: str, body: FolderUpdate) -> FolderOut:
    from core.memory.store import get_store
    store = await get_store()
    f = await store.rename_folder(folder_id, body.name)
    if f is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderOut(id=f.id, name=f.name, created_at=f.created_at.isoformat())


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(folder_id: str) -> None:
    from core.memory.store import get_store
    store = await get_store()
    ok = await store.delete_folder(folder_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Folder not found")
