"""
ROSA OS — macOS API (Phase 5).

POST /api/mac/run        {script_type, command}
GET  /api/mac/status
POST /api/mac/notify     {title, body}
GET  /api/mac/screenshot
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.mac")
router = APIRouter(prefix="/api/mac", tags=["mac"])


class RunRequest(BaseModel):
    script_type: str = "shell"   # shell | applescript
    command: str


class NotifyRequest(BaseModel):
    title: str
    body: str


@router.post("/run")
async def run_command(req: RunRequest):
    try:
        from core.mac.controller import get_mac_controller
        ctrl = get_mac_controller()
        if req.script_type == "applescript":
            result = ctrl.run_applescript(req.command)
        else:
            result = ctrl.run_shell(req.command, safe=True)
        return {"success": True, "result": result, "script_type": req.script_type}
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/status")
async def mac_status():
    from core.mac.watcher import get_system_status
    return await get_system_status()


@router.post("/notify")
async def notify(req: NotifyRequest):
    from core.mac.controller import get_mac_controller
    ok = get_mac_controller().send_notification(req.title, req.body)
    return {"success": ok}


@router.get("/screenshot")
async def screenshot():
    from core.mac.controller import get_mac_controller
    data = get_mac_controller().take_screenshot()
    if not data:
        raise HTTPException(500, "Screenshot failed")
    return {"success": True, "base64": data}


@router.get("/apps")
async def running_apps():
    from core.mac.controller import get_mac_controller
    return {"apps": get_mac_controller().get_running_apps()}


@router.get("/system")
async def system_info():
    from core.mac.controller import get_mac_controller
    return get_mac_controller().get_system_info()
