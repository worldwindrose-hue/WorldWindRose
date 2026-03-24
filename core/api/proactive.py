"""
ROSA OS — Proactive Scheduler API.
Controls morning briefings and subscription checks.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/proactive", tags=["proactive"])


class SubscriptionCreate(BaseModel):
    name: str
    source_type: str  # "rss" | "github" | "tiktok"
    source_url: str
    keywords: list[str] = []


@router.get("/briefing", response_model=dict)
async def get_briefing() -> dict:
    """Generate an on-demand morning briefing."""
    from core.prediction.proactive import get_briefing_now
    return await get_briefing_now()


@router.get("/status", response_model=dict)
async def scheduler_status() -> dict:
    """Return scheduler running status."""
    from core.prediction.proactive import is_running
    return {"running": is_running()}


@router.post("/start", response_model=dict)
async def start_scheduler() -> dict:
    """Start the proactive scheduler."""
    from core.prediction.proactive import start_scheduler, is_running
    start_scheduler()
    return {"running": is_running(), "message": "Scheduler started"}


@router.post("/stop", response_model=dict)
async def stop_scheduler() -> dict:
    """Stop the proactive scheduler."""
    from core.prediction.proactive import stop_scheduler, is_running
    stop_scheduler()
    return {"running": is_running(), "message": "Scheduler stopped"}


@router.get("/habits", response_model=dict)
async def habit_summary() -> dict:
    """Return habit graph summary."""
    from core.prediction.habit_graph import get_habit_graph
    return get_habit_graph().summary()


@router.get("/inference", response_model=dict)
async def belief_state() -> dict:
    """Return active inference belief state."""
    from core.prediction.active_inference import get_state
    return get_state()


@router.get("/subscriptions", response_model=list)
async def list_subscriptions() -> list:
    """List all subscriptions."""
    from core.memory.store import get_store
    store = await get_store()
    subs = await store.list_subscriptions()
    return [
        {
            "id": s.id,
            "name": s.name,
            "source_type": s.source_type,
            "source_url": s.source_url,
            "enabled": s.enabled,
            "last_checked": s.last_checked.isoformat() if s.last_checked else None,
        }
        for s in subs
    ]


@router.post("/subscriptions", response_model=dict)
async def create_subscription(req: SubscriptionCreate) -> dict:
    """Create a new subscription."""
    import json
    from core.memory.store import get_store
    store = await get_store()
    sub = await store.create_subscription(
        name=req.name,
        source_type=req.source_type,
        source_url=req.source_url,
        keywords=json.dumps(req.keywords),
    )
    return {
        "id": sub.id,
        "name": sub.name,
        "source_type": sub.source_type,
        "enabled": sub.enabled,
    }
