"""
ROSA OS — Pattern Analyzer.

Builds a behavioral profile of the user from conversation history,
task patterns, and interaction times. Used for personalized briefings
and proactive suggestions.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.prediction.patterns")

_PROFILE_FILE = Path("memory/user_profile.json")


@dataclass
class UserProfile:
    """Persisted user behavioral profile."""
    # Activity patterns
    active_hours: list[int] = field(default_factory=list)      # 0-23 hours with most activity
    active_days: list[str] = field(default_factory=list)        # Mon/Tue/etc
    avg_session_length_min: float = 0.0
    total_sessions: int = 0

    # Topic interests (topic → frequency)
    top_topics: dict[str, int] = field(default_factory=dict)

    # Behavior traits
    prefers_short_answers: bool = False
    uses_voice: bool = False
    language: str = "ru"  # primary language

    # Task stats
    tasks_completed_week: int = 0
    tasks_pending: int = 0

    # Streak
    days_streak: int = 0
    last_active: str = ""

    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "UserProfile":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class PatternAnalyzer:
    """
    Analyzes conversation history and task logs to build user profile.
    All analysis is local — no data leaves the device.
    """

    def __init__(self):
        self._profile = self._load_profile()

    def _load_profile(self) -> UserProfile:
        if _PROFILE_FILE.exists():
            try:
                return UserProfile.from_dict(json.loads(_PROFILE_FILE.read_text()))
            except Exception:
                pass
        return UserProfile()

    def _save_profile(self) -> None:
        try:
            _PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self._profile.updated_at = datetime.now(timezone.utc).isoformat()
            _PROFILE_FILE.write_text(json.dumps(self._profile.to_dict(), indent=2, ensure_ascii=False))
        except Exception as exc:
            logger.debug("Profile save error: %s", exc)

    # ── Analysis ──────────────────────────────────────────────────────────

    def record_interaction(
        self,
        message: str,
        hour: Optional[int] = None,
        weekday: Optional[int] = None,
        response_length: int = 0,
    ) -> None:
        """Record a single interaction for pattern building."""
        now = datetime.now()
        h = hour if hour is not None else now.hour
        d = weekday if weekday is not None else now.weekday()

        # Active hours (keep top 6)
        hour_counts = Counter(self._profile.active_hours)
        hour_counts[h] += 1
        self._profile.active_hours = [
            h for h, _ in hour_counts.most_common(6)
        ]

        # Active days
        day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        day_name = day_names[d % 7]
        day_counts = Counter(self._profile.active_days)
        day_counts[day_name] += 1
        self._profile.active_days = [d for d, _ in day_counts.most_common(3)]

        # Language detection
        ru_chars = sum(1 for c in message if "\u0400" <= c <= "\u04ff")
        if ru_chars > len(message) * 0.2:
            self._profile.language = "ru"
        elif len(message) > 10:
            self._profile.language = "en"

        # Short answer preference
        if response_length < 200 and response_length > 0:
            self._profile.prefers_short_answers = True

        # Topics (naive keyword extraction)
        topics = self._extract_topics(message)
        for topic in topics:
            self._profile.top_topics[topic] = self._profile.top_topics.get(topic, 0) + 1

        # Keep top 20 topics
        if len(self._profile.top_topics) > 20:
            sorted_topics = sorted(self._profile.top_topics.items(), key=lambda x: x[1], reverse=True)
            self._profile.top_topics = dict(sorted_topics[:20])

        self._profile.total_sessions += 1
        self._profile.last_active = datetime.now(timezone.utc).isoformat()
        self._save_profile()

    def _extract_topics(self, text: str) -> list[str]:
        """Very simple keyword-based topic extraction."""
        _TOPIC_KEYWORDS: dict[str, list[str]] = {
            "программирование": ["код", "python", "функция", "error", "bug", "api", "класс"],
            "задачи": ["задача", "сделать", "план", "список", "напомни"],
            "поиск": ["найди", "поищи", "информация", "что такое", "расскажи"],
            "анализ": ["анализ", "статистика", "данные", "график", "таблица"],
            "творчество": ["напиши", "придумай", "текст", "идея", "история"],
            "общение": ["привет", "как дела", "спасибо", "пожалуйста"],
        }
        text_lower = text.lower()
        found = []
        for topic, keywords in _TOPIC_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                found.append(topic)
        return found[:3]

    async def analyze_history(self, days: int = 7) -> UserProfile:
        """Analyze conversation history from DB to update profile."""
        try:
            from core.memory.store import get_store
            store = await get_store()
            turns = await store.list_turns(limit=200)

            for turn in turns:
                if turn.role == "user":
                    self.record_interaction(
                        message=turn.content,
                        response_length=len(turn.content),
                    )
        except Exception as exc:
            logger.debug("History analysis failed: %s", exc)

        # Task stats
        try:
            from core.memory.store import get_store
            store = await get_store()
            tasks = await store.list_tasks(status="completed", limit=50)
            self._profile.tasks_completed_week = len(tasks)
            pending = await store.list_tasks(status="pending", limit=50)
            self._profile.tasks_pending = len(pending)
        except Exception:
            pass

        self._save_profile()
        return self._profile

    def get_profile(self) -> UserProfile:
        return self._profile

    def get_personalization_hints(self) -> dict:
        """Return hints for personalizing responses."""
        p = self._profile
        return {
            "language": p.language,
            "prefers_short": p.prefers_short_answers,
            "active_hours": p.active_hours[:3],
            "top_topics": list(p.top_topics.keys())[:5],
            "days_streak": p.days_streak,
        }

    def build_morning_context(self) -> str:
        """Build a personalized morning briefing context string."""
        p = self._profile
        parts = []
        if p.top_topics:
            top = list(p.top_topics.keys())[:3]
            parts.append(f"Основные интересы: {', '.join(top)}")
        if p.tasks_pending > 0:
            parts.append(f"Незавершённых задач: {p.tasks_pending}")
        if p.active_hours:
            h = p.active_hours[0]
            parts.append(f"Обычно активен около {h}:00")
        return "; ".join(parts) if parts else "Профиль пуст"

    def build_weekly_summary(self) -> str:
        """Build a weekly activity summary string."""
        p = self._profile
        return (
            f"За неделю выполнено задач: {p.tasks_completed_week}. "
            f"Активных дней: {len(p.active_days)}. "
            f"Топ темы: {', '.join(list(p.top_topics.keys())[:3]) or 'нет данных'}."
        )


_analyzer: Optional[PatternAnalyzer] = None


def get_pattern_analyzer() -> PatternAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = PatternAnalyzer()
    return _analyzer
