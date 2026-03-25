"""
ROSA OS — Prediction & Pattern API.

Endpoints for user profile, behavioral patterns, morning briefing, weekly report.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, BackgroundTasks

logger = logging.getLogger("rosa.api.prediction")

router = APIRouter(prefix="/api/prediction", tags=["prediction"])


@router.get("/profile")
async def get_user_profile():
    """Return the current user behavioral profile."""
    try:
        from core.prediction.pattern_analyzer import get_pattern_analyzer
        return get_pattern_analyzer().get_profile().to_dict()
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/profile/analyze")
async def analyze_profile(background_tasks: BackgroundTasks):
    """Trigger background profile analysis from conversation history."""
    try:
        from core.prediction.pattern_analyzer import get_pattern_analyzer

        async def _run():
            await get_pattern_analyzer().analyze_history()

        background_tasks.add_task(_run)
        return {"status": "started"}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/hints")
async def personalization_hints():
    """Return personalization hints for response tuning."""
    try:
        from core.prediction.pattern_analyzer import get_pattern_analyzer
        return get_pattern_analyzer().get_personalization_hints()
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/morning-brief")
async def get_morning_brief():
    """Return a morning briefing context string."""
    try:
        from core.prediction.pattern_analyzer import get_pattern_analyzer
        ctx = get_pattern_analyzer().build_morning_context()
        return {"brief": ctx}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/weekly-report")
async def get_weekly_report():
    """Return a weekly activity summary."""
    try:
        from core.prediction.pattern_analyzer import get_pattern_analyzer
        summary = get_pattern_analyzer().build_weekly_summary()
        return {"report": summary}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/record")
async def record_interaction(message: str, response_length: int = 0):
    """Record a user interaction for pattern building."""
    try:
        from core.prediction.pattern_analyzer import get_pattern_analyzer
        get_pattern_analyzer().record_interaction(message, response_length=response_length)
        return {"status": "recorded"}
    except Exception as exc:
        return {"error": str(exc)}
