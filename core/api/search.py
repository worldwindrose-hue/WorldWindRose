"""
ROSA OS — Search API (Phase 4).

POST /api/search                  {query, depth, sources}
POST /api/search/subscribe        {topic, interval}
GET  /api/search/subscriptions
DELETE /api/search/subscribe/{topic}
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from core.search.hypersearch import get_hypersearch
from core.search.live_monitor import get_live_monitor

logger = logging.getLogger("rosa.api.search")
router = APIRouter(prefix="/api/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    depth: str = "normal"   # fast | normal | deep
    sources: list[str] | None = None
    synthesize: bool = True


class SubscribeRequest(BaseModel):
    topic: str
    interval: int = 3600
    notify_telegram: bool = True


@router.post("")
async def search(req: SearchRequest):
    return await get_hypersearch().search(
        query=req.query,
        depth=req.depth,
        sources=req.sources,
        synthesize=req.synthesize,
    )


@router.post("/subscribe")
async def subscribe(req: SubscribeRequest):
    monitor = get_live_monitor()
    monitor.subscribe(req.topic, req.interval, req.notify_telegram)
    if not monitor._running:
        monitor.start()
    return {"status": "subscribed", "topic": req.topic, "interval": req.interval}


@router.get("/subscriptions")
async def list_subscriptions():
    return get_live_monitor().list_subscriptions()


@router.delete("/subscribe/{topic:path}")
async def unsubscribe(topic: str):
    get_live_monitor().unsubscribe(topic)
    return {"status": "unsubscribed", "topic": topic}
