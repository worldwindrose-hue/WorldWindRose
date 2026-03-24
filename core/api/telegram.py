"""
ROSA OS — Telegram API endpoints.

POST /api/telegram/webhook    — receive updates from Telegram
POST /api/telegram/send       — send message to owner
GET  /api/telegram/status
POST /api/telegram/webhook/set
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.telegram")
router = APIRouter(prefix="/api/telegram", tags=["telegram"])


class SendRequest(BaseModel):
    chat_id: str | int
    text: str


class WebhookSetRequest(BaseModel):
    webhook_url: str


@router.post("/webhook")
async def webhook(update: dict):
    """Receive and process Telegram update."""
    from core.mobile.telegram_gateway import process_webhook_update
    return await process_webhook_update(update)


@router.post("/send")
async def send(req: SendRequest):
    from core.mobile.telegram_gateway import send_message
    ok = await send_message(req.chat_id, req.text)
    return {"success": ok}


@router.get("/status")
async def telegram_status():
    from core.mobile.telegram_gateway import is_configured
    return {"configured": is_configured()}


@router.post("/webhook/set")
async def set_webhook(req: WebhookSetRequest):
    from core.mobile.telegram_gateway import set_webhook
    return await set_webhook(req.webhook_url)
