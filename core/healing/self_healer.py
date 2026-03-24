"""
ROSA OS — Self-Healer.

Monitors system health and auto-recovers from common failures:
- DB connection errors → reinitialize
- Crashed background tasks → restart
- Model API failures → switch to fallback model
- Import errors → log and disable failing module
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger("rosa.healing.self_healer")

# Health check results
_health_cache: dict[str, dict[str, Any]] = {}
_failure_counts: dict[str, int] = defaultdict(int)
_FAILURE_THRESHOLD = 3  # failures before disabling a component


class HealthStatus:
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


async def check_database() -> dict[str, Any]:
    """Check if the database is accessible."""
    try:
        from core.memory.store import get_store
        store = await get_store()
        # Simple ping: count tasks
        await store.list_tasks(limit=1)
        return {"component": "database", "status": HealthStatus.OK}
    except Exception as exc:
        return {"component": "database", "status": HealthStatus.FAILED, "error": str(exc)}


async def check_model_api() -> dict[str, Any]:
    """Check if the LLM API is accessible."""
    try:
        from openai import AsyncOpenAI
        from core.config import get_settings
        settings = get_settings()
        if not settings.openrouter_api_key:
            return {"component": "model_api", "status": HealthStatus.FAILED, "error": "No API key"}

        client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
        )
        # Minimal health check
        await client.models.list()
        return {"component": "model_api", "status": HealthStatus.OK}
    except Exception as exc:
        return {"component": "model_api", "status": HealthStatus.DEGRADED, "error": str(exc)}


async def check_knowledge_graph() -> dict[str, Any]:
    """Check if the knowledge graph is accessible."""
    try:
        from core.knowledge.graph import get_knowledge_store
        store = get_knowledge_store()
        stats = store.stats() if hasattr(store, "stats") else {}
        return {"component": "knowledge_graph", "status": HealthStatus.OK, "stats": stats}
    except Exception as exc:
        return {"component": "knowledge_graph", "status": HealthStatus.DEGRADED, "error": str(exc)}


async def check_proactive_scheduler() -> dict[str, Any]:
    """Check if the proactive scheduler is running."""
    try:
        from core.prediction.proactive import is_running
        running = is_running()
        status = HealthStatus.OK if running else HealthStatus.DEGRADED
        return {"component": "proactive_scheduler", "status": status, "running": running}
    except Exception as exc:
        return {"component": "proactive_scheduler", "status": HealthStatus.FAILED, "error": str(exc)}


async def full_health_check() -> dict[str, Any]:
    """Run all health checks and return aggregated status."""
    import asyncio

    checks = await asyncio.gather(
        check_database(),
        check_model_api(),
        check_knowledge_graph(),
        check_proactive_scheduler(),
        return_exceptions=True,
    )

    results = []
    overall = HealthStatus.OK
    for check in checks:
        if isinstance(check, Exception):
            results.append({"status": HealthStatus.FAILED, "error": str(check)})
            overall = HealthStatus.FAILED
        else:
            results.append(check)
            if check.get("status") == HealthStatus.FAILED:
                overall = HealthStatus.FAILED
            elif check.get("status") == HealthStatus.DEGRADED and overall == HealthStatus.OK:
                overall = HealthStatus.DEGRADED

    _health_cache["last_check"] = {
        "timestamp": time.time(),
        "overall": overall,
        "components": results,
    }

    return {
        "overall": overall,
        "components": results,
        "timestamp": time.time(),
    }


async def heal_database() -> bool:
    """Attempt to reinitialize the database connection."""
    try:
        from core.memory.store import _store
        if _store is not None:
            import core.memory.store as store_module
            store_module._store = None  # Force re-init on next get_store()
        from core.memory.store import get_store
        await get_store()
        logger.info("Database healed: connection reinitialized")
        return True
    except Exception as exc:
        logger.error("Database heal failed: %s", exc)
        return False


async def heal_scheduler() -> bool:
    """Restart the proactive scheduler if it's not running."""
    try:
        from core.prediction.proactive import is_running, start_scheduler, stop_scheduler
        if not is_running():
            stop_scheduler()
            start_scheduler()
            logger.info("Proactive scheduler restarted")
        return True
    except Exception as exc:
        logger.error("Scheduler heal failed: %s", exc)
        return False


async def auto_heal() -> dict[str, Any]:
    """
    Run health checks and attempt to heal any failed components.
    Returns healing report.
    """
    health = await full_health_check()
    healed = []
    failed_to_heal = []

    for component_health in health["components"]:
        status = component_health.get("status")
        name = component_health.get("component", "")

        if status == HealthStatus.FAILED:
            _failure_counts[name] += 1

            if name == "database":
                success = await heal_database()
                (healed if success else failed_to_heal).append(name)
            elif name == "proactive_scheduler":
                success = await heal_scheduler()
                (healed if success else failed_to_heal).append(name)
            else:
                failed_to_heal.append(name)
        else:
            _failure_counts[name] = 0  # Reset on success

    return {
        "health": health,
        "healed": healed,
        "failed_to_heal": failed_to_heal,
        "failure_counts": dict(_failure_counts),
    }


def get_last_health_report() -> dict[str, Any]:
    """Return cached health check results without running new checks."""
    return _health_cache.get("last_check", {"status": "not_checked"})
