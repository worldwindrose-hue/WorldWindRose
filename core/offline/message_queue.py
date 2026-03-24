"""
ROSA OS — Offline Message Queue (Phase 6).

When Rosa is offline, incoming messages are stored here.
When connectivity is restored, they're processed in order.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.offline.queue")

_QUEUE_FILE = Path("memory/offline_queue.json")


def _load_queue() -> list[dict[str, Any]]:
    if not _QUEUE_FILE.exists():
        return []
    try:
        return json.loads(_QUEUE_FILE.read_text())
    except Exception:
        return []


def _save_queue(queue: list[dict[str, Any]]) -> None:
    _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _QUEUE_FILE.write_text(json.dumps(queue, ensure_ascii=False, indent=2))


def enqueue(message: str, sender: str = "telegram", metadata: dict | None = None) -> None:
    """Add a message to the offline queue."""
    queue = _load_queue()
    queue.append({
        "id": str(len(queue) + 1),
        "message": message,
        "sender": sender,
        "metadata": metadata or {},
        "queued_at": datetime.now(timezone.utc).isoformat(),
    })
    _save_queue(queue)
    logger.info("Queued offline message from %s: %s", sender, message[:50])


def get_queue() -> list[dict[str, Any]]:
    return _load_queue()


def clear_queue() -> int:
    queue = _load_queue()
    n = len(queue)
    _save_queue([])
    return n


async def process_queue() -> list[dict[str, Any]]:
    """Process all queued messages and clear queue."""
    queue = _load_queue()
    if not queue:
        return []

    logger.info("Processing %d queued messages", len(queue))
    results = []

    for item in queue:
        try:
            from core.router import get_router
            rosa = get_router()
            result = await rosa.chat(
                message=item["message"],
                session_id=item.get("metadata", {}).get("session_id", "offline"),
            )
            reply = result.get("response", "")

            # Attempt to send reply back to Telegram
            if item.get("sender") == "telegram":
                try:
                    from core.mobile.telegram_gateway import send_notification
                    await send_notification(f"📬 Ответ на ваш вопрос:\n\n{reply[:500]}")
                except Exception:
                    pass

            results.append({"message": item["message"], "response": reply, "processed": True})
        except Exception as exc:
            logger.error("Queue processing failed for item: %s", exc)
            results.append({"message": item["message"], "error": str(exc), "processed": False})

    clear_queue()
    return results
