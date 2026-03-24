"""
ROSA OS — Audit API.

Endpoints for startup audit, self-debug, and regression testing.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks

logger = logging.getLogger("rosa.api.audit")

router = APIRouter(prefix="/api/audit", tags=["audit"])


# ── STARTUP AUDIT ─────────────────────────────────────────────────────────


@router.get("/startup")
async def get_startup_audit():
    """Return the most recent startup audit report."""
    try:
        from core.audit.startup_audit import get_last_audit, run_startup_audit
        report = get_last_audit()
        if report is None:
            report = await run_startup_audit()
        return report.to_dict()
    except Exception as exc:
        logger.error("Startup audit error: %s", exc)
        return {"error": str(exc)}


@router.post("/startup/run")
async def run_audit_now():
    """Run a fresh startup audit immediately."""
    try:
        from core.audit.startup_audit import run_startup_audit
        report = await run_startup_audit()
        return report.to_dict()
    except Exception as exc:
        logger.error("Startup audit run error: %s", exc)
        return {"error": str(exc)}


# ── SELF DEBUGGER ──────────────────────────────────────────────────────────


@router.get("/debug")
async def get_debug_report():
    """Return the most recent debug scan results."""
    try:
        from core.audit.self_debugger import get_self_debugger
        debugger = get_self_debugger()
        report = debugger.run()
        import dataclasses
        return dataclasses.asdict(report)
    except Exception as exc:
        logger.error("Debug report error: %s", exc)
        return {"error": str(exc)}


# ── REGRESSION TESTER ─────────────────────────────────────────────────────


@router.post("/regression/run")
async def run_regression(background_tasks: BackgroundTasks):
    """Trigger a regression test run in the background."""
    try:
        from core.audit.regression_tester import get_regression_tester
        tester = get_regression_tester()

        async def _run():
            await tester.run_tests()

        background_tasks.add_task(_run)
        return {"status": "started", "message": "Regression tests running in background"}
    except Exception as exc:
        logger.error("Regression trigger error: %s", exc)
        return {"error": str(exc)}


@router.get("/regression/history")
async def get_regression_history(limit: int = 20):
    """Get regression test history."""
    try:
        from core.audit.regression_tester import get_regression_tester
        tester = get_regression_tester()
        import dataclasses
        return {
            "history": [dataclasses.asdict(r) for r in tester.get_history(limit)],
            "trend": tester.get_trend(),
        }
    except Exception as exc:
        logger.error("Regression history error: %s", exc)
        return {"error": str(exc)}
