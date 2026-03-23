"""
ROSA OS — Metrics collector for self-improvement cycle.
Gathers failed tasks, low-rated tasks, and high-severity events from memory.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("rosa.self_improvement.collector")


class Collector:
    """Collects failure signals from memory for the improvement cycle."""

    async def collect(self) -> dict[str, Any]:
        """
        Gather metrics from the memory store.

        Returns a dict with:
            has_issues: bool
            failed_tasks: list of task dicts
            low_rated_tasks: list of task dicts
            high_severity_events: list of event dicts
            summary: human-readable summary string
        """
        try:
            from core.memory.store import get_store
            store = await get_store()
        except Exception as exc:
            logger.error("Collector: cannot connect to store: %s", exc)
            return {"has_issues": False, "error": str(exc)}

        failed_tasks = await store.get_failed_tasks(limit=50)
        low_rated_tasks = await store.get_low_rated_tasks(max_rating=2, limit=50)
        high_events = await store.get_high_severity_events(limit=50)

        has_issues = bool(failed_tasks or low_rated_tasks or high_events)

        summary_parts = []
        if failed_tasks:
            summary_parts.append(f"{len(failed_tasks)} failed task(s)")
        if low_rated_tasks:
            summary_parts.append(f"{len(low_rated_tasks)} low-rated task(s) (rating ≤2)")
        if high_events:
            summary_parts.append(f"{len(high_events)} high-severity event(s)")

        summary = "Found: " + ", ".join(summary_parts) if summary_parts else "No issues found"

        logger.info("Collector: %s", summary)

        return {
            "has_issues": has_issues,
            "failed_tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "plan": t.plan,
                    "result": t.result,
                    "status": t.status,
                    "created_at": t.created_at.isoformat(),
                }
                for t in failed_tasks
            ],
            "low_rated_tasks": [
                {
                    "id": t.id,
                    "description": t.description,
                    "result": t.result,
                    "owner_rating": t.owner_rating,
                    "created_at": t.created_at.isoformat(),
                }
                for t in low_rated_tasks
            ],
            "high_severity_events": [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "description": e.description,
                    "severity": e.severity,
                    "created_at": e.created_at.isoformat(),
                }
                for e in high_events
            ],
            "summary": summary,
        }
