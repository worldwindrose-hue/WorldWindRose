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


# ── Self-Deploy endpoints ────────────────────────────────────────────────────

class DeployRequest(BaseModel):
    branch: str = "claude/vigilant-almeida"
    restart_service: bool = True


@router.post("/git/pull")
async def git_pull(req: DeployRequest):
    """Pull latest code from GitHub and optionally restart the service."""
    import subprocess, asyncio
    results = {}

    try:
        # Stash any local changes
        sp = subprocess.run(
            ["git", "-C", "/opt/rosa", "stash"],
            capture_output=True, text=True, timeout=30
        )
        results["stash"] = sp.stdout.strip() or sp.stderr.strip()

        # Pull
        sp = subprocess.run(
            ["git", "-C", "/opt/rosa", "pull", "origin", req.branch],
            capture_output=True, text=True, timeout=60
        )
        results["pull"] = sp.stdout.strip() + sp.stderr.strip()
        results["returncode"] = sp.returncode

        if req.restart_service and sp.returncode == 0:
            # Restart in background (service restarts us so we can't await it)
            subprocess.Popen(
                ["systemctl", "restart", "rosa-assistant"],
                start_new_session=True
            )
            results["restart"] = "queued"

        return {"status": "ok", **results}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.post("/deploy/self")
async def self_deploy():
    """Full self-deploy: pull latest code + restart."""
    return await git_pull(DeployRequest(restart_service=True))


@router.post("/service/restart")
async def restart_service():
    """Restart the rosa-assistant systemd service."""
    import subprocess
    subprocess.Popen(["systemctl", "restart", "rosa-assistant"], start_new_session=True)
    return {"status": "restart_queued", "message": "Service restart initiated"}


@router.get("/service/status")
async def service_status():
    """Check systemd service status."""
    import subprocess
    sp = subprocess.run(
        ["systemctl", "is-active", "rosa-assistant"],
        capture_output=True, text=True
    )
    active = sp.stdout.strip()
    sp2 = subprocess.run(
        ["systemctl", "show", "rosa-assistant", "--property=MainPID,ActiveEnterTimestamp,MemoryCurrent"],
        capture_output=True, text=True
    )
    props = dict(line.split("=", 1) for line in sp2.stdout.strip().splitlines() if "=" in line)
    return {"active": active, "properties": props}
