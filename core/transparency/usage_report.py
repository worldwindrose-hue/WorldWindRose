"""
ROSA OS — Usage Tracker & Report Generator.

Tracks API token usage, request counts, cost estimates.
Generates daily/weekly usage reports.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.transparency.usage")

_USAGE_FILE = Path("memory/usage_stats.json")

# Approximate cost per 1M tokens (USD)
_COST_PER_1M: dict[str, float] = {
    "moonshotai/kimi-k2.5": 0.15,
    "anthropic/claude-3-5-haiku": 0.25,
    "anthropic/claude-3-5-sonnet": 3.0,
    "ollama/local": 0.0,
    "cache": 0.0,
}


@dataclass
class DayStats:
    date: str  # YYYY-MM-DD
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hits: int = 0
    errors: int = 0
    models: dict[str, int] = field(default_factory=dict)  # model → request count

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        cost = 0.0
        for model, count in self.models.items():
            rate = _COST_PER_1M.get(model, 0.5)
            # Rough estimate: avg 500 tokens/request
            cost += count * 500 / 1_000_000 * rate
        return round(cost, 4)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["total_tokens"] = self.total_tokens
        d["estimated_cost_usd"] = self.estimated_cost_usd
        return d


class UsageTracker:
    """Tracks per-day token usage and generates reports."""

    def __init__(self):
        self._days: dict[str, DayStats] = {}
        self._load()

    def _load(self) -> None:
        if not _USAGE_FILE.exists():
            return
        try:
            data = json.loads(_USAGE_FILE.read_text())
            for day_dict in data.get("days", []):
                stats = DayStats(**{k: v for k, v in day_dict.items()
                                    if k in DayStats.__dataclass_fields__})
                self._days[stats.date] = stats
        except Exception as exc:
            logger.debug("Usage load error: %s", exc)

    def _save(self) -> None:
        try:
            _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _USAGE_FILE.write_text(
                json.dumps(
                    {"days": [d.to_dict() for d in self._days.values()]},
                    indent=2, ensure_ascii=False,
                )
            )
        except Exception:
            pass

    def _today(self) -> str:
        return date.today().isoformat()

    def _get_day(self, day: str | None = None) -> DayStats:
        key = day or self._today()
        if key not in self._days:
            self._days[key] = DayStats(date=key)
        return self._days[key]

    def record_request(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error: bool = False,
        cached: bool = False,
    ) -> None:
        day = self._get_day()
        day.requests += 1
        day.input_tokens += input_tokens
        day.output_tokens += output_tokens
        if error:
            day.errors += 1
        if cached:
            day.cache_hits += 1
        day.models[model] = day.models.get(model, 0) + 1
        self._save()

    def get_today(self) -> DayStats:
        return self._get_day()

    def get_week(self) -> list[DayStats]:
        today = date.today()
        result = []
        for i in range(7):
            d = (today - timedelta(days=i)).isoformat()
            result.append(self._days.get(d, DayStats(date=d)))
        return list(reversed(result))

    def get_totals(self, days: int = 30) -> dict:
        """Return aggregate stats for the last N days."""
        today = date.today()
        total_requests = 0
        total_tokens = 0
        total_cost = 0.0
        total_errors = 0
        total_cache = 0

        for i in range(days):
            d = (today - timedelta(days=i)).isoformat()
            s = self._days.get(d)
            if s:
                total_requests += s.requests
                total_tokens += s.total_tokens
                total_cost += s.estimated_cost_usd
                total_errors += s.errors
                total_cache += s.cache_hits

        return {
            "days": days,
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "total_errors": total_errors,
            "cache_hits": total_cache,
            "cache_rate": round(total_cache / max(total_requests, 1) * 100, 1),
        }

    def generate_weekly_report(self) -> str:
        week = self.get_week()
        total_req = sum(d.requests for d in week)
        total_tok = sum(d.total_tokens for d in week)
        total_cost = sum(d.estimated_cost_usd for d in week)

        # Find busiest day
        busiest = max(week, key=lambda d: d.requests)

        lines = [
            f"📊 Еженедельный отчёт по использованию ROSA:",
            f"  Запросов за 7 дней: {total_req}",
            f"  Всего токенов: {total_tok:,}",
            f"  Оценочная стоимость: ${total_cost:.4f}",
            f"  Самый активный день: {busiest.date} ({busiest.requests} запросов)",
        ]
        return "\n".join(lines)


_tracker: Optional[UsageTracker] = None


def get_usage_tracker() -> UsageTracker:
    global _tracker
    if _tracker is None:
        _tracker = UsageTracker()
    return _tracker
