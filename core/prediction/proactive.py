"""
ROSA OS — Proactive Scheduler.

Runs background async tasks to deliver morning briefings,
check subscriptions, and trigger habit-based suggestions.

Default: morning briefing at 07:00 local time.
Subscriptions: checked on their configured schedule.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.prediction.proactive")

_scheduler_task: asyncio.Task | None = None
_running = False


async def _morning_briefing() -> dict[str, Any]:
    """
    Generate a morning briefing by querying:
    - Top habit predictions for the day
    - Pending tasks from DB
    - Any active subscriptions with fresh content
    """
    from core.prediction.habit_graph import get_habit_graph
    now = datetime.now()
    graph = get_habit_graph()
    predictions = graph.predict_next_task(now.hour, now.weekday())

    # Pending tasks
    pending_tasks: list[dict] = []
    try:
        from core.memory.store import get_store
        store = await get_store()
        tasks = await store.list_tasks(status="pending")
        pending_tasks = [{"title": t.title, "priority": getattr(t, "priority", 2)} for t in tasks[:5]]
    except Exception as exc:
        logger.debug("Could not load pending tasks: %s", exc)

    briefing = {
        "type": "morning_briefing",
        "timestamp": now.isoformat(),
        "predictions": predictions[:3],
        "pending_tasks": pending_tasks,
        "message": _format_briefing(now, predictions, pending_tasks),
    }
    logger.info("Morning briefing generated: %d predictions, %d tasks", len(predictions), len(pending_tasks))
    return briefing


def _format_briefing(
    now: datetime,
    predictions: list[dict],
    tasks: list[dict],
) -> str:
    lines = [f"Доброе утро! {now.strftime('%A, %d %B %Y')}"]
    if predictions:
        top = predictions[0]["task_type"]
        lines.append(f"Вероятно, сегодня вас интересует: {top}")
    if tasks:
        lines.append(f"Незавершённых задач: {len(tasks)}")
        for t in tasks[:3]:
            lines.append(f"  • {t['title']}")
    lines.append("Чем могу помочь?")
    return "\n".join(lines)


async def check_subscriptions() -> list[dict[str, Any]]:
    """Check all enabled subscriptions and return fresh content summaries."""
    results = []
    try:
        from core.memory.store import get_store
        store = await get_store()
        subs = await store.list_subscriptions(enabled_only=True)
        for sub in subs:
            try:
                result = await _fetch_subscription(sub)
                if result:
                    results.append(result)
                    await store.touch_subscription(sub.id)
            except Exception as exc:
                logger.debug("Subscription %s check failed: %s", sub.id, exc)
    except Exception as exc:
        logger.debug("list_subscriptions failed: %s", exc)
    return results


async def _fetch_subscription(sub: Any) -> dict[str, Any] | None:
    """Fetch content for a single subscription based on source_type."""
    source_type = getattr(sub, "source_type", "")
    source_url = getattr(sub, "source_url", "")
    keywords = getattr(sub, "keywords", "[]")

    if not source_url:
        return None

    if source_type == "rss":
        return await _fetch_rss(sub.name, source_url)
    elif source_type == "github":
        return {"name": sub.name, "type": "github", "url": source_url, "note": "GitHub check pending"}
    elif source_type == "tiktok":
        return {"name": sub.name, "type": "tiktok", "url": source_url, "note": "TikTok check pending"}
    return None


async def _fetch_rss(name: str, url: str) -> dict[str, Any] | None:
    """Minimal RSS fetch via httpx."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            # Very basic title extraction
            import re
            titles = re.findall(r"<title>(.*?)</title>", r.text)
            return {
                "name": name,
                "type": "rss",
                "url": url,
                "items": titles[1:4] if len(titles) > 1 else [],
            }
    except Exception as exc:
        logger.debug("RSS fetch failed for %s: %s", url, exc)
        return None


async def _scheduler_loop() -> None:
    """Main scheduler loop — runs continuously until stopped."""
    global _running
    logger.info("Proactive scheduler started")

    while _running:
        now = datetime.now()

        # Morning briefing at 07:00
        if now.hour == 7 and now.minute == 0:
            try:
                from core.status.tracker import set_status, RosaStatus
                set_status(RosaStatus.ACTING, "Генерирую утренний брифинг")
            except Exception:
                pass
            try:
                briefing = await _morning_briefing()
                logger.info("Morning briefing: %s", briefing["message"][:80])
            except Exception as exc:
                logger.error("Morning briefing failed: %s", exc)

        # Check subscriptions every hour at :30
        if now.minute == 30:
            try:
                await check_subscriptions()
            except Exception as exc:
                logger.error("Subscription check failed: %s", exc)

        # Sleep until next minute
        await asyncio.sleep(60)


def start_scheduler() -> None:
    """Start the background scheduler loop (idempotent)."""
    global _scheduler_task, _running
    if _running:
        logger.debug("Scheduler already running")
        return
    _running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Proactive scheduler task created")


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    global _scheduler_task, _running
    _running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
    logger.info("Proactive scheduler stopped")


def is_running() -> bool:
    return _running and _scheduler_task is not None and not _scheduler_task.done()


async def get_briefing_now() -> dict[str, Any]:
    """Generate an on-demand briefing (not waiting for 07:00)."""
    return await _morning_briefing()
