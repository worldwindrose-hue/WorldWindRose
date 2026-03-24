"""
ROSA OS — Habit Graph.

Builds a temporal pattern model from conversation history.
Tracks: hour_of_day × task_type → frequency weights.
Used by ProactiveScheduler to predict user needs.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger("rosa.prediction.habit_graph")

# 24 hours × task_type counts
_HabitMatrix = dict[str, dict[int, int]]  # task_type → {hour: count}


class HabitGraph:
    """
    Tracks when users tend to ask about specific topics.
    Stores counts in a (task_type × hour) matrix.
    Also tracks day_of_week patterns.
    """

    def __init__(self) -> None:
        # task_type → {hour_of_day: count}
        self._hour_matrix: _HabitMatrix = defaultdict(lambda: defaultdict(int))
        # task_type → {day_of_week (0=Mon): count}
        self._day_matrix: _HabitMatrix = defaultdict(lambda: defaultdict(int))
        # raw event count
        self._total_events = 0

    def record(self, task_type: str, hour: int, day_of_week: int) -> None:
        """Record a usage event."""
        self._hour_matrix[task_type][hour] += 1
        self._day_matrix[task_type][day_of_week] += 1
        self._total_events += 1

    def top_hours_for(self, task_type: str, top_n: int = 3) -> list[tuple[int, int]]:
        """Return top N (hour, count) pairs for a task type."""
        hour_counts = self._hour_matrix.get(task_type, {})
        sorted_hours = sorted(hour_counts.items(), key=lambda x: -x[1])
        return sorted_hours[:top_n]

    def top_task_types(self, top_n: int = 5) -> list[tuple[str, int]]:
        """Return top N task types by total usage."""
        totals: dict[str, int] = {}
        for task_type, hour_counts in self._hour_matrix.items():
            totals[task_type] = sum(hour_counts.values())
        return sorted(totals.items(), key=lambda x: -x[1])[:top_n]

    def predict_next_task(self, current_hour: int, current_day: int) -> list[dict[str, Any]]:
        """
        Given current hour + day, return ranked task types by predicted relevance.
        Score = hour_weight * 0.7 + day_weight * 0.3 (normalized).
        """
        if self._total_events == 0:
            return []

        scores: dict[str, float] = {}
        all_types = set(self._hour_matrix) | set(self._day_matrix)

        for task_type in all_types:
            hour_total = sum(self._hour_matrix[task_type].values()) or 1
            day_total = sum(self._day_matrix[task_type].values()) or 1

            hour_w = self._hour_matrix[task_type].get(current_hour, 0) / hour_total
            day_w = self._day_matrix[task_type].get(current_day, 0) / day_total

            scores[task_type] = hour_w * 0.7 + day_w * 0.3

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [
            {"task_type": t, "score": round(s, 4)}
            for t, s in ranked
            if s > 0
        ]

    def summary(self) -> dict[str, Any]:
        """Return a summary of recorded habits."""
        return {
            "total_events": self._total_events,
            "task_types": len(self._hour_matrix),
            "top_tasks": self.top_task_types(5),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage."""
        return {
            "hour_matrix": {
                k: dict(v) for k, v in self._hour_matrix.items()
            },
            "day_matrix": {
                k: dict(v) for k, v in self._day_matrix.items()
            },
            "total_events": self._total_events,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HabitGraph":
        """Deserialize from storage."""
        graph = cls()
        for task_type, hour_counts in data.get("hour_matrix", {}).items():
            for hour_str, count in hour_counts.items():
                graph._hour_matrix[task_type][int(hour_str)] = count
        for task_type, day_counts in data.get("day_matrix", {}).items():
            for day_str, count in day_counts.items():
                graph._day_matrix[task_type][int(day_str)] = count
        graph._total_events = data.get("total_events", 0)
        return graph


# Module-level singleton
_habit_graph: HabitGraph | None = None


def get_habit_graph() -> HabitGraph:
    global _habit_graph
    if _habit_graph is None:
        _habit_graph = HabitGraph()
    return _habit_graph


async def record_usage(task_type: str, hour: int, day_of_week: int) -> None:
    """Record a usage event and persist to DB if available."""
    get_habit_graph().record(task_type, hour, day_of_week)
    try:
        from core.memory.store import get_store
        store = await get_store()
        await store.record_habit_event(
            hour_of_day=hour,
            day_of_week=day_of_week,
            task_type=task_type,
        )
    except Exception as exc:
        logger.debug("Habit event DB persist failed: %s", exc)
