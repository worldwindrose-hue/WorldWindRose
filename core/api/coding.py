"""
ROSA OS — Coding API (Phase 7).

POST /api/coding/execute    {language, code}
POST /api/coding/write      {path, task}
POST /api/coding/refactor   {path, instruction}
GET  /api/coding/git/log
GET  /api/coding/git/diff
GET  /api/coding/git/status
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.coding")
router = APIRouter(prefix="/api/coding", tags=["coding"])


class ExecuteRequest(BaseModel):
    language: str = "python"
    code: str
    timeout: int = 30


class WriteModuleRequest(BaseModel):
    path: str
    task: str
    auto_test: bool = True


class RefactorRequest(BaseModel):
    path: str
    instruction: str


@router.post("/execute")
async def execute_code(req: ExecuteRequest):
    from core.coding.code_executor import execute_code
    return await execute_code(req.language, req.code, req.timeout)


@router.post("/execute/explain")
async def execute_and_explain(req: ExecuteRequest):
    from core.coding.self_coder import execute_and_explain
    return await execute_and_explain(req.code, req.language)


@router.post("/write")
async def write_module(req: WriteModuleRequest):
    try:
        from core.coding.self_coder import write_module
        return await write_module(req.path, req.task, req.auto_test)
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.post("/refactor")
async def refactor_module(req: RefactorRequest):
    from core.coding.self_coder import refactor_module
    return await refactor_module(req.path, req.instruction)


@router.get("/git/log")
async def git_log(limit: int = 10):
    from core.coding.git_manager import get_git_manager
    return {"commits": get_git_manager().get_log(limit)}


@router.get("/git/diff")
async def git_diff(staged: bool = False):
    from core.coding.git_manager import get_git_manager
    return {"diff": get_git_manager().get_diff(staged)}


@router.get("/git/status")
async def git_status():
    from core.coding.git_manager import get_git_manager
    gm = get_git_manager()
    return {
        "status": gm.get_status(),
        "branch": gm.get_current_branch(),
        "changed_files": gm.get_changed_files(),
    }
