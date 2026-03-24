"""
ROSA OS — Gap Analyzer.

Weekly analysis of Rosa's weaknesses based on self-reflection logs.
Clusters failures, generates learning plans, creates Ouroboros tasks.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.metacognition.self_reflection import load_reflections
from core.metacognition.capability_map import get_capability_map

logger = logging.getLogger("rosa.metacognition.gaps")

_REPORT_FILE = Path("memory/gap_reports.jsonl")


async def weekly_gap_report(days: int = 7) -> dict[str, Any]:
    """
    Analyse reflections from last N days.
    Returns {gaps, learning_plan, priority_tasks, score_trend}.
    """
    reflections = load_reflections(limit=500)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    recent = []
    for r in reflections:
        try:
            ts = datetime.fromisoformat(r.get("timestamp", ""))
            if ts > cutoff:
                recent.append(r)
        except Exception:
            recent.append(r)  # include if timestamp parse fails

    if not recent:
        return {
            "period_days": days,
            "responses_analyzed": 0,
            "gaps": [],
            "learning_plan": [],
            "priority_tasks": [],
            "avg_score": 0.0,
            "score_trend": "no_data",
        }

    # Score trend
    scores = [r.get("score", 0.5) for r in recent]
    avg_score = round(sum(scores) / len(scores), 3)
    first_half = scores[: len(scores) // 2]
    second_half = scores[len(scores) // 2 :]
    avg_first = sum(first_half) / max(len(first_half), 1)
    avg_second = sum(second_half) / max(len(second_half), 1)
    trend = "improving" if avg_second > avg_first + 0.05 else (
        "declining" if avg_second < avg_first - 0.05 else "stable"
    )

    # Collect all gaps
    all_gaps: list[str] = []
    all_improvement_tasks: list[str] = []
    for r in recent:
        all_gaps.extend(r.get("gaps", []))
        all_improvement_tasks.extend(r.get("improvement_tasks", []))

    # Count gap frequency
    gap_counts = Counter(all_gaps)
    top_gaps = [{"gap": g, "frequency": c} for g, c in gap_counts.most_common(10)]

    task_counts = Counter(all_improvement_tasks)
    priority_tasks = [t for t, _ in task_counts.most_common(5)]

    # Get capability gaps
    cap_gaps = get_capability_map().get_gaps()
    cap_gap_names = [c.name for c in cap_gaps[:5]]

    # Generate learning plan
    learning_plan = _generate_learning_plan(top_gaps[:3], cap_gap_names)

    report = {
        "period_days": days,
        "responses_analyzed": len(recent),
        "avg_score": avg_score,
        "score_trend": trend,
        "gaps": top_gaps,
        "capability_gaps": cap_gap_names,
        "learning_plan": learning_plan,
        "priority_tasks": priority_tasks,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Save report
    try:
        _REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_REPORT_FILE, "a") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Failed to save gap report: %s", exc)

    return report


def _generate_learning_plan(
    gaps: list[dict], cap_gaps: list[str]
) -> list[dict]:
    """Generate structured learning plan from gaps."""
    plan = []

    for gap_info in gaps:
        gap = gap_info.get("gap", "")
        if not gap:
            continue
        plan.append({
            "topic": gap,
            "actions": [
                f"Изучить тему: {gap}",
                f"Найти 3 примера использования",
                f"Написать тест для проверки знаний",
            ],
            "priority": "high" if gap_info.get("frequency", 0) > 3 else "medium",
        })

    for cap_name in cap_gaps:
        plan.append({
            "topic": f"Улучшить способность: {cap_name}",
            "actions": [
                f"Практиковать {cap_name} на реальных задачах",
                f"Найти паттерны успешных решений",
                f"Обновить capability_map после улучшения",
            ],
            "priority": "medium",
        })

    return plan[:6]


def get_last_report() -> dict | None:
    """Load last saved gap report."""
    if not _REPORT_FILE.exists():
        return None
    try:
        lines = _REPORT_FILE.read_text().strip().splitlines()
        if lines:
            return json.loads(lines[-1])
    except Exception:
        pass
    return None
