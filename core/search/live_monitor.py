"""
ROSA OS — Live Topic Monitor (Phase 4).

Monitors topics in real-time via periodic HyperSearch.
New findings → notify via Telegram → save to Knowledge Graph.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.search.live_monitor")

@dataclass
class TopicSubscription:
    topic: str
    interval: int = 3600   # seconds
    last_checked: str = field(default_factory=lambda: "")
    notify_telegram: bool = True


class LiveMonitor:
    def __init__(self) -> None:
        self._subscriptions: list[TopicSubscription] = []
        self._task: asyncio.Task | None = None
        self._running = False

    def subscribe(self, topic: str, interval: int = 3600, notify_telegram: bool = True) -> None:
        # Remove duplicates
        self._subscriptions = [s for s in self._subscriptions if s.topic != topic]
        self._subscriptions.append(TopicSubscription(topic=topic, interval=interval, notify_telegram=notify_telegram))
        logger.info("Subscribed to topic: %s (every %ds)", topic, interval)

    def unsubscribe(self, topic: str) -> None:
        self._subscriptions = [s for s in self._subscriptions if s.topic != topic]

    def list_subscriptions(self) -> list[dict[str, Any]]:
        return [
            {"topic": s.topic, "interval": s.interval, "last_checked": s.last_checked}
            for s in self._subscriptions
        ]

    async def check_topic(self, topic: str) -> dict[str, Any]:
        """Immediately check a topic and return results."""
        from core.search.hypersearch import get_hypersearch
        result = await get_hypersearch().search(topic, depth="normal")
        return result

    async def _monitor_loop(self) -> None:
        while self._running:
            now = datetime.now(timezone.utc)
            for sub in list(self._subscriptions):
                last = sub.last_checked
                if not last or (now.timestamp() - datetime.fromisoformat(last).timestamp()) >= sub.interval:
                    try:
                        result = await self.check_topic(sub.topic)
                        sub.last_checked = now.isoformat()
                        if sub.notify_telegram and result.get("synthesis"):
                            await self._notify(sub.topic, result["synthesis"][:500])
                    except Exception as exc:
                        logger.debug("Monitor check failed for %s: %s", sub.topic, exc)
            await asyncio.sleep(60)

    async def _notify(self, topic: str, summary: str) -> None:
        """Attempt to send Telegram notification."""
        try:
            from core.mobile.telegram_gateway import send_notification
            await send_notification(f"🔍 Новое по теме «{topic}»:\n\n{summary}")
        except Exception:
            pass

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()


_monitor: LiveMonitor | None = None


def get_live_monitor() -> LiveMonitor:
    global _monitor
    if _monitor is None:
        _monitor = LiveMonitor()
    return _monitor
