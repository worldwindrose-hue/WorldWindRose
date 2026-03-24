"""
ROSA OS — Telegram User Connector via Telethon (MTProto API).
Reads personal chat history and ingests it into the knowledge graph.

Setup:
1. Get API credentials from https://my.telegram.org/apps
2. Add to .env:
   TELEGRAM_API_ID=123456
   TELEGRAM_API_HASH=abcdef...
   TELEGRAM_PHONE=+79991234567
3. First run: call start_auth() → verify_auth(code) to generate session
4. Session stored as TELEGRAM_SESSION string in .env
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("rosa.integrations.telegram_user")

REQUIRED_ENV_VARS = ["TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELEGRAM_PHONE"]
SETUP_INSTRUCTIONS = """
Telegram (пользовательский аккаунт через Telethon):
1. Зайдите на https://my.telegram.org/apps
2. Создайте приложение, получите API ID и API Hash
3. Добавьте в .env:
   TELEGRAM_API_ID=ваш_id
   TELEGRAM_API_HASH=ваш_hash
   TELEGRAM_PHONE=+79991234567
4. Вызовите POST /api/integrations/telegram/auth/start
5. Введите OTP из Telegram → POST /api/integrations/telegram/auth/verify
6. После этого можно читать историю чатов
Зависимость: pip install telethon (уже установлен)
"""

# Хранилище phone_code_hash между вызовами start/verify
_pending_auth: dict[str, str] = {}


def _is_configured() -> bool:
    return all(os.getenv(v) for v in REQUIRED_ENV_VARS)


def _get_client():
    """Create a Telethon TelegramClient with StringSession."""
    try:
        from telethon import TelegramClient  # type: ignore
        from telethon.sessions import StringSession  # type: ignore
    except ImportError:
        raise RuntimeError("telethon not installed. Run: pip install telethon")

    api_id = int(os.getenv("TELEGRAM_API_ID", "0"))
    api_hash = os.getenv("TELEGRAM_API_HASH", "")
    session_str = os.getenv("TELEGRAM_SESSION", "")
    return TelegramClient(StringSession(session_str), api_id, api_hash)


async def start_auth() -> dict[str, str]:
    """Send OTP to the user's phone. Returns phone_code_hash for verify step."""
    if not _is_configured():
        raise ValueError(f"Missing env vars: {REQUIRED_ENV_VARS}")
    phone = os.getenv("TELEGRAM_PHONE", "")
    client = _get_client()
    await client.connect()
    result = await client.send_code_request(phone)
    _pending_auth["phone_code_hash"] = result.phone_code_hash
    await client.disconnect()
    return {"status": "code_sent", "phone": phone}


async def verify_auth(code: str) -> dict[str, str]:
    """Verify OTP and save session string to env (in-process only)."""
    phone = os.getenv("TELEGRAM_PHONE", "")
    phone_code_hash = _pending_auth.get("phone_code_hash")
    if not phone_code_hash:
        raise ValueError("Auth not started. Call start_auth() first.")

    client = _get_client()
    await client.connect()
    await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
    session_string = client.session.save()
    await client.disconnect()

    # Store in process env (user should also add to .env manually)
    os.environ["TELEGRAM_SESSION"] = session_string
    _pending_auth.clear()
    return {
        "status": "authenticated",
        "session_hint": "Add TELEGRAM_SESSION to your .env file to persist across restarts.",
        "session_length": len(session_string),
    }


async def read_messages(chat_id: str | int, limit: int = 100) -> list[dict[str, Any]]:
    """Read recent messages from a Telegram chat/channel."""
    if not _is_configured():
        raise ValueError(f"Missing env vars: {REQUIRED_ENV_VARS}")
    if not os.getenv("TELEGRAM_SESSION"):
        raise ValueError("Not authenticated. Call start_auth() + verify_auth() first.")

    client = _get_client()
    await client.connect()

    messages: list[dict[str, Any]] = []
    async for msg in client.iter_messages(chat_id, limit=limit):
        if not msg.text:
            continue
        sender = ""
        try:
            sender_obj = await msg.get_sender()
            if sender_obj:
                sender = getattr(sender_obj, "username", "") or getattr(sender_obj, "first_name", "")
        except Exception:
            pass
        messages.append({
            "id": msg.id,
            "text": msg.text,
            "sender": sender,
            "date": msg.date.isoformat() if msg.date else "",
            "chat_id": str(chat_id),
        })

    await client.disconnect()
    return messages


async def import_to_graph(chat_id: str | int, limit: int = 100) -> dict[str, Any]:
    """Read messages and push to knowledge graph via add_from_dialog()."""
    from core.knowledge.graph import add_from_dialog

    messages = await read_messages(chat_id, limit)
    if not messages:
        return {"nodes_created": 0, "messages_processed": 0}

    total_nodes = 0
    batch_size = 10

    for i in range(0, len(messages), batch_size):
        batch = messages[i : i + batch_size]
        combined = " | ".join(m["text"][:200] for m in batch if m.get("text"))
        if combined.strip():
            r = await add_from_dialog(combined, session_id=f"telegram:{chat_id}")
            total_nodes += r.get("nodes_created", 0)

    return {
        "messages_processed": len(messages),
        "nodes_created": total_nodes,
        "chat_id": str(chat_id),
    }
