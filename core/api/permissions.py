"""
ROSA OS — Permission Request System
POST /api/permissions/request   — Rosa creates a pending action request
POST /api/permissions/approve   — User approves or rejects a request
GET  /api/permissions/pending   — List all pending requests
GET  /api/permissions/history   — List completed requests
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.permissions")
router = APIRouter(prefix="/api/permissions", tags=["permissions"])

# ── In-memory store (survives requests, reset on restart) ──────────────────
_requests: dict[str, "PermissionItem"] = {}


class PermissionItem(BaseModel):
    id: str
    action: str          # e.g. "git push origin main"
    level: int           # 1, 2, 3
    description: str
    status: Literal["pending", "approved", "rejected", "expired"] = "pending"
    created_at: datetime = datetime.now(timezone.utc)
    expires_at: datetime = datetime.now(timezone.utc) + timedelta(minutes=30)
    approved_at: datetime | None = None
    note: str = ""       # user comment on approval/rejection


class RequestIn(BaseModel):
    action: str
    level: int
    description: str


class ApproveIn(BaseModel):
    id: str
    confirmed: bool
    note: str = ""


class PermissionOut(BaseModel):
    id: str
    action: str
    level: int
    description: str
    status: str
    created_at: datetime
    expires_at: datetime
    approved_at: datetime | None
    note: str


def _expire_old() -> None:
    """Mark expired pending requests automatically."""
    now = datetime.now(timezone.utc)
    for item in _requests.values():
        if item.status == "pending" and now > item.expires_at:
            item.status = "expired"


def _to_out(item: PermissionItem) -> PermissionOut:
    return PermissionOut(
        id=item.id, action=item.action, level=item.level,
        description=item.description, status=item.status,
        created_at=item.created_at, expires_at=item.expires_at,
        approved_at=item.approved_at, note=item.note,
    )


@router.post("/request", response_model=PermissionOut, status_code=201)
async def request_permission(req: RequestIn) -> PermissionOut:
    """Rosa calls this to request permission for a level-2 or level-3 action."""
    if req.level not in (1, 2, 3):
        raise HTTPException(400, "level must be 1, 2, or 3")

    item = PermissionItem(
        id=str(uuid.uuid4()),
        action=req.action,
        level=req.level,
        description=req.description,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    _requests[item.id] = item
    logger.info("Permission requested: level=%d action=%r id=%s", req.level, req.action, item.id)
    return _to_out(item)


@router.post("/approve", response_model=PermissionOut)
async def approve_permission(req: ApproveIn) -> PermissionOut:
    """User approves or rejects a pending permission request."""
    _expire_old()
    item = _requests.get(req.id)
    if not item:
        raise HTTPException(404, f"Permission request {req.id} not found")
    if item.status != "pending":
        raise HTTPException(409, f"Request is already {item.status}")

    item.status = "approved" if req.confirmed else "rejected"
    item.approved_at = datetime.now(timezone.utc)
    item.note = req.note
    logger.info("Permission %s: id=%s action=%r", item.status, item.id, item.action)
    return _to_out(item)


@router.get("/pending", response_model=list[PermissionOut])
async def list_pending() -> list[PermissionOut]:
    """Return all pending permission requests."""
    _expire_old()
    return [_to_out(i) for i in _requests.values() if i.status == "pending"]


@router.get("/history", response_model=list[PermissionOut])
async def list_history(limit: int = 50) -> list[PermissionOut]:
    """Return completed permission requests, newest first."""
    _expire_old()
    done = [i for i in _requests.values() if i.status != "pending"]
    done.sort(key=lambda x: x.created_at, reverse=True)
    return [_to_out(i) for i in done[:limit]]


@router.delete("/clear")
async def clear_history() -> dict:
    """Clear all non-pending requests from memory."""
    to_remove = [k for k, v in _requests.items() if v.status != "pending"]
    for k in to_remove:
        del _requests[k]
    return {"cleared": len(to_remove)}
