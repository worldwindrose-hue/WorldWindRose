"""
ROSA OS — Cache API.

Endpoints for managing the response cache and local router stats.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter

logger = logging.getLogger("rosa.api.cache")

router = APIRouter(prefix="/api/cache", tags=["cache"])


@router.get("/stats")
async def cache_stats():
    """Return cache hit/miss statistics."""
    try:
        from core.router.cache_manager import get_cache_manager
        return get_cache_manager().stats()
    except Exception as exc:
        logger.error("Cache stats error: %s", exc)
        return {"error": str(exc)}


@router.post("/purge")
async def purge_expired():
    """Remove expired cache entries."""
    try:
        from core.router.cache_manager import get_cache_manager
        removed = get_cache_manager().purge_expired()
        return {"removed": removed}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/clear")
async def clear_cache():
    """Clear all cache entries."""
    try:
        from core.router.cache_manager import get_cache_manager
        removed = get_cache_manager().clear()
        return {"cleared": removed}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/router/stats")
async def router_stats():
    """Return local router routing statistics."""
    try:
        from core.router.local_router import get_local_router
        return get_local_router().stats()
    except Exception as exc:
        return {"error": str(exc)}
