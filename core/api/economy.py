"""
ROSA OS — Token Economy API.

GET  /api/economy/stats
GET  /api/economy/alternatives?model=...
GET  /api/economy/estimate?daily=100&tokens=500
GET  /api/economy/env
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

logger = logging.getLogger("rosa.api.economy")
router = APIRouter(prefix="/api/economy", tags=["economy"])


@router.get("/stats")
async def economy_stats():
    from core.economy.token_optimizer import get_usage_stats
    return get_usage_stats()


@router.get("/alternatives")
async def suggest_alternatives(model: str = Query(...)):
    from core.economy.api_extractor import suggest_free_alternatives
    return {"model": model, "alternatives": suggest_free_alternatives(model)}


@router.get("/estimate")
async def estimate_cost(daily: int = Query(default=100), tokens: int = Query(default=500)):
    from core.economy.api_extractor import estimate_monthly_cost
    return {"estimates_usd_per_month": estimate_monthly_cost(daily, tokens)}


@router.get("/env")
async def scan_env():
    from core.economy.api_extractor import scan_env_files
    return scan_env_files()
