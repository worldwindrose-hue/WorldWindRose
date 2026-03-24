"""
ROSA OS — Telegram Gateway (Phase 6).

Connects Rosa to Telegram Bot API.
Architecture: Telegram → Bot webhook → /api/telegram/webhook → Rosa API → reply

Requires:
  TELEGRAM_BOT_TOKEN in .env

Features:
  - Any message → /api/chat → reply in Telegram
  - Voice → text (via Whisper if available) → chat
  - Photo → /api/vision/screenshot/analyze → reply
  - /status → current Rosa status
  - /act <task> → autonomous agent
  - Push notifications from Rosa to Telegram
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("rosa.mobile.telegram_gateway")


async def send_message(chat_id: str | int, text: str, bot_token: str | None = None) -> bool:
    """Send a Telegram message."""
    try:
        from core.config import get_settings
        settings = get_settings()
        token = bot_token or getattr(settings, "telegram_bot_token", "")
        if not token:
            logger.debug("No TELEGRAM_BOT_TOKEN — cannot send message")
            return False
        import httpx
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
            return r.status_code == 200
    except Exception as exc:
        logger.debug("Telegram send failed: %s", exc)
        return False


async def send_notification(text: str) -> bool:
    """Send notification to owner's Telegram chat."""
    try:
        from core.config import get_settings
        settings = get_settings()
        owner_chat_id = getattr(settings, "telegram_owner_chat_id", "")
        if not owner_chat_id:
            return False
        return await send_message(owner_chat_id, text)
    except Exception as exc:
        logger.debug("Notification failed: %s", exc)
        return False


def is_configured() -> bool:
    """Check if Telegram bot is configured."""
    try:
        from core.config import get_settings
        settings = get_settings()
        return bool(getattr(settings, "telegram_bot_token", ""))
    except Exception:
        return False


async def set_webhook(webhook_url: str, bot_token: str | None = None) -> dict[str, Any]:
    """Register webhook URL with Telegram."""
    try:
        from core.config import get_settings
        settings = get_settings()
        token = bot_token or getattr(settings, "telegram_bot_token", "")
        import httpx
        url = f"https://api.telegram.org/bot{token}/setWebhook"
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json={"url": webhook_url})
            return r.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


async def process_webhook_update(update: dict[str, Any]) -> dict[str, Any]:
    """Process an incoming Telegram update and reply to user."""
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()

    if not chat_id or not text:
        return {"processed": False}

    # Built-in commands
    if text == "/status":
        try:
            from core.status.tracker import get_tracker
            evt = get_tracker().get_current()
            reply = f"🌹 ROSA OS Status\n{evt.status}: {evt.detail}"
        except Exception:
            reply = "🌹 ROSA OS — работает"
        await send_message(chat_id, reply)
        return {"processed": True, "command": "status"}

    if text.startswith("/act "):
        task = text[5:].strip()
        # Queue as autonomous task
        try:
            from core.offline.message_queue import enqueue
            enqueue(task, sender="telegram", metadata={"chat_id": chat_id})
        except Exception:
            pass
        await send_message(chat_id, f"✅ Задача принята: {task[:100]}")
        return {"processed": True, "command": "act"}

    # Check internet
    from core.offline.local_mode import get_online_status
    if not await get_online_status():
        from core.offline.message_queue import enqueue
        enqueue(text, sender="telegram", metadata={"chat_id": chat_id})
        await send_message(chat_id, "📴 Роза сейчас офлайн. Сообщение сохранено и будет обработано при восстановлении связи.")
        return {"processed": True, "queued": True}

    # Regular chat
    try:
        from core.router import get_router
        rosa = get_router()
        result = await rosa.chat(message=text, session_id=f"telegram_{chat_id}")
        reply = result.get("response", "Нет ответа")
        await send_message(chat_id, reply[:4000])
        return {"processed": True, "response": reply[:100]}
    except Exception as exc:
        logger.error("Telegram chat failed: %s", exc)
        await send_message(chat_id, "⚠️ Ошибка обработки запроса.")
        return {"processed": False, "error": str(exc)}
