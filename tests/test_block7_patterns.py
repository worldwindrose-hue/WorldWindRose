"""Tests for Block 7 — PatternAnalyzer + proactive briefings."""
from __future__ import annotations

import pytest
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── PatternAnalyzer ───────────────────────────────────────────────────────


class TestPatternAnalyzer:
    def test_analyzer_singleton(self):
        """get_pattern_analyzer() returns same instance."""
        from core.prediction.pattern_analyzer import get_pattern_analyzer, PatternAnalyzer
        a = get_pattern_analyzer()
        b = get_pattern_analyzer()
        assert a is b
        assert isinstance(a, PatternAnalyzer)

    def test_record_interaction_updates_hours(self):
        """record_interaction updates active_hours."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        analyzer._profile.active_hours = []

        analyzer.record_interaction("Привет, как дела?", hour=9)
        assert 9 in analyzer._profile.active_hours

    def test_record_interaction_detects_russian(self):
        """Language detection identifies Russian text."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        analyzer.record_interaction("Привет! Как дела сегодня? Помоги мне с задачей.")
        assert analyzer._profile.language == "ru"

    def test_record_interaction_detects_english(self):
        """Language detection identifies English text."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        analyzer.record_interaction("Hello, can you help me write some Python code today?")
        assert analyzer._profile.language == "en"

    def test_record_interaction_extracts_topics(self):
        """Topics are extracted from interaction."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        analyzer._profile.top_topics = {}

        analyzer.record_interaction("напиши код на python с классом и функцией")
        assert len(analyzer._profile.top_topics) > 0

    def test_record_interaction_updates_days(self):
        """Active days are updated."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        analyzer._profile.active_days = []

        analyzer.record_interaction("test", weekday=0)  # Monday
        assert len(analyzer._profile.active_days) > 0

    def test_extract_topics_programming(self):
        """Programming keywords extract correct topic."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        topics = analyzer._extract_topics("Напиши python функцию для сортировки")
        assert "программирование" in topics

    def test_extract_topics_task(self):
        """Task keywords extract correct topic."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        topics = analyzer._extract_topics("добавь задача в список и план")
        assert "задачи" in topics

    def test_get_personalization_hints(self):
        """get_personalization_hints returns dict with required fields."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        hints = analyzer.get_personalization_hints()
        assert "language" in hints
        assert "prefers_short" in hints
        assert "active_hours" in hints
        assert "top_topics" in hints

    def test_build_morning_context_empty(self):
        """Morning context with empty profile returns fallback."""
        from core.prediction.pattern_analyzer import PatternAnalyzer, UserProfile
        analyzer = PatternAnalyzer()
        analyzer._profile = UserProfile()
        ctx = analyzer.build_morning_context()
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_build_morning_context_with_data(self):
        """Morning context includes task info."""
        from core.prediction.pattern_analyzer import PatternAnalyzer, UserProfile
        analyzer = PatternAnalyzer()
        analyzer._profile = UserProfile(
            top_topics={"программирование": 5, "задачи": 3},
            tasks_pending=3,
            active_hours=[9, 10, 14],
        )
        ctx = analyzer.build_morning_context()
        assert "3" in ctx  # pending tasks
        assert "программирование" in ctx or "задачи" in ctx

    def test_build_weekly_summary(self):
        """Weekly summary contains task count."""
        from core.prediction.pattern_analyzer import PatternAnalyzer, UserProfile
        analyzer = PatternAnalyzer()
        analyzer._profile = UserProfile(
            tasks_completed_week=12,
            active_days=["Пн", "Вт", "Ср"],
            top_topics={"программирование": 10},
        )
        summary = analyzer.build_weekly_summary()
        assert "12" in summary
        assert isinstance(summary, str)

    def test_profile_serialization(self):
        """UserProfile serializes and deserializes correctly."""
        from core.prediction.pattern_analyzer import UserProfile
        profile = UserProfile(
            active_hours=[9, 10, 14],
            language="ru",
            top_topics={"программирование": 5},
            tasks_completed_week=7,
        )
        d = profile.to_dict()
        restored = UserProfile.from_dict(d)
        assert restored.language == "ru"
        assert restored.tasks_completed_week == 7
        assert restored.active_hours == [9, 10, 14]

    def test_profile_saves_to_file(self, tmp_path):
        """Profile is saved to disk."""
        from core.prediction import pattern_analyzer
        original = pattern_analyzer._PROFILE_FILE
        pattern_analyzer._PROFILE_FILE = tmp_path / "user_profile.json"

        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        analyzer.record_interaction("test message for saving", hour=10)

        assert pattern_analyzer._PROFILE_FILE.exists()
        data = json.loads(pattern_analyzer._PROFILE_FILE.read_text())
        assert "active_hours" in data
        pattern_analyzer._PROFILE_FILE = original

    @pytest.mark.asyncio
    async def test_analyze_history_empty(self):
        """analyze_history doesn't crash with empty DB."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()

        mock_store = AsyncMock()
        mock_store.list_turns = AsyncMock(return_value=[])
        mock_store.list_tasks = AsyncMock(return_value=[])

        with patch("core.memory.store.get_store", return_value=mock_store):
            profile = await analyzer.analyze_history()

        assert profile is not None

    @pytest.mark.asyncio
    async def test_analyze_history_with_turns(self):
        """analyze_history processes conversation turns."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        analyzer._profile.total_sessions = 0

        turn1 = MagicMock()
        turn1.role = "user"
        turn1.content = "Привет! Помоги написать python код"
        turn2 = MagicMock()
        turn2.role = "assistant"
        turn2.content = "Конечно!"

        mock_store = AsyncMock()
        mock_store.list_turns = AsyncMock(return_value=[turn1, turn2])
        mock_store.list_tasks = AsyncMock(return_value=[])

        with patch("core.memory.store.get_store", return_value=mock_store):
            profile = await analyzer.analyze_history()

        assert profile.total_sessions > 0

    def test_top_topics_trimmed_to_20(self):
        """top_topics dict is trimmed to max 20 entries."""
        from core.prediction.pattern_analyzer import PatternAnalyzer
        analyzer = PatternAnalyzer()
        analyzer._profile.top_topics = {}

        # Add 30 interactions with unique topics (via _extract_topics overriding)
        for i in range(25):
            analyzer._profile.top_topics[f"topic_{i}"] = i

        analyzer.record_interaction("Привет тест")
        assert len(analyzer._profile.top_topics) <= 20
