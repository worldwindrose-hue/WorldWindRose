"""
ROSA OS — Filesystem API.

GET  /api/fs/list?path=...
GET  /api/fs/read?path=...
POST /api/fs/write {path, content}
GET  /api/fs/search?q=...&root=...
GET  /api/fs/tree?root=...&depth=3
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.filesystem.manager import get_fs_manager

logger = logging.getLogger("rosa.api.fs")
router = APIRouter(prefix="/api/fs", tags=["filesystem"])


class WriteRequest(BaseModel):
    path: str
    content: str


@router.get("/list")
async def list_dir(path: str = Query(default="~/Desktop/Rosa_Assistant/")):
    try:
        return get_fs_manager().list_dir(path)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except NotADirectoryError as e:
        raise HTTPException(400, str(e))


@router.get("/read")
async def read_file(path: str = Query(...)):
    try:
        content = get_fs_manager().read_file(path)
        return {"path": path, "content": content, "length": len(content)}
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/write")
async def write_file(req: WriteRequest):
    try:
        return get_fs_manager().write_file(req.path, req.content)
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/search")
async def search_files(
    q: str = Query(...),
    root: str = Query(default="~/Desktop/Rosa_Assistant/"),
    ext: str | None = Query(default=None),
):
    extensions = [f".{ext.lstrip('.')}" ] if ext else None
    try:
        return get_fs_manager().search_files(q, root=root, extensions=extensions)
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/tree")
async def file_tree(
    root: str = Query(default="~/Desktop/Rosa_Assistant/"),
    depth: int = Query(default=3, ge=1, le=6),
):
    try:
        return get_fs_manager().get_file_tree(root=root, depth=depth)
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/zones")
async def allowed_zones():
    return {"zones": get_fs_manager().allowed_zones()}
