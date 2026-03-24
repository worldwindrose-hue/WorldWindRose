"""ROSA OS — Web Push Notifications API."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class SubscribeRequest(BaseModel):
    subscription: dict[str, Any]


class SendRequest(BaseModel):
    title: str
    body: str
    url: str = "/"
    tag: str = "rosa"


@router.get("/vapid-key")
async def get_vapid_key():
    """Return VAPID public key for frontend subscription setup."""
    from core.notifications.web_push import get_push_manager
    key = get_push_manager().public_key()
    return {"public_key": key, "available": key is not None}


@router.post("/subscribe")
async def subscribe(req: SubscribeRequest):
    """Register a push subscription."""
    from core.notifications.web_push import get_push_manager
    get_push_manager().subscribe(req.subscription)
    return {"success": True, "subscribers": get_push_manager().subscribers_count()}


@router.delete("/subscribe")
async def unsubscribe(endpoint: str):
    """Remove a push subscription."""
    from core.notifications.web_push import get_push_manager
    get_push_manager().unsubscribe(endpoint)
    return {"success": True}


@router.post("/send")
async def send_notification(req: SendRequest):
    """Send a push notification to all subscribers."""
    from core.notifications.web_push import get_push_manager
    result = await get_push_manager().notify(req.title, req.body, req.url, req.tag)
    return result


@router.get("/status")
async def notification_status():
    from core.notifications.web_push import get_push_manager
    mgr = get_push_manager()
    return {
        "push_available": mgr.public_key() is not None,
        "subscribers": mgr.subscribers_count(),
        "public_key": mgr.public_key(),
    }
