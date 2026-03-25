"""
ROSA OS — Transparency API.

Endpoints for chain-of-thought traces, usage reports, kernel integrity.
"""

from __future__ import annotations

import logging
from fastapi import APIRouter

logger = logging.getLogger("rosa.api.transparency")

router = APIRouter(prefix="/api/transparency", tags=["transparency"])


# ── Chain of Thought ──────────────────────────────────────────────────────


@router.get("/cot/recent")
async def get_recent_cot(limit: int = 10):
    """Return recent chain-of-thought traces."""
    try:
        from core.transparency.chain_of_thought import get_cot_visualizer
        traces = get_cot_visualizer().get_recent_traces(limit)
        return [t.to_dict() for t in traces]
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/cot/{trace_id}")
async def get_cot_trace(trace_id: str):
    """Return a specific CoT trace by ID."""
    try:
        from core.transparency.chain_of_thought import get_cot_visualizer
        trace = get_cot_visualizer().get_trace(trace_id)
        if trace is None:
            from fastapi import HTTPException
            raise HTTPException(404, f"Trace {trace_id} not found")
        return trace.to_dict()
    except Exception as exc:
        return {"error": str(exc)}


# ── Usage Tracker ─────────────────────────────────────────────────────────


@router.get("/usage/today")
async def get_usage_today():
    """Return today's usage statistics."""
    try:
        from core.transparency.usage_report import get_usage_tracker
        return get_usage_tracker().get_today().to_dict()
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/usage/week")
async def get_usage_week():
    """Return last 7 days of usage statistics."""
    try:
        from core.transparency.usage_report import get_usage_tracker
        return [d.to_dict() for d in get_usage_tracker().get_week()]
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/usage/totals")
async def get_usage_totals(days: int = 30):
    """Return aggregate usage for last N days."""
    try:
        from core.transparency.usage_report import get_usage_tracker
        return get_usage_tracker().get_totals(days)
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/usage/report")
async def get_weekly_report():
    """Return a formatted weekly usage report."""
    try:
        from core.transparency.usage_report import get_usage_tracker
        return {"report": get_usage_tracker().generate_weekly_report()}
    except Exception as exc:
        return {"error": str(exc)}


# ── Immutable Kernel ──────────────────────────────────────────────────────


@router.get("/kernel/status")
async def kernel_status():
    """Return kernel integrity status."""
    try:
        from core.security.immutable_kernel import get_immutable_kernel
        kernel = get_immutable_kernel()
        report = kernel.verify()
        return report.to_dict()
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/kernel/seal")
async def seal_kernel():
    """Seal the kernel (record current file hashes). Run after setup."""
    try:
        from core.security.immutable_kernel import get_immutable_kernel
        count = get_immutable_kernel().seal()
        return {"sealed": count}
    except Exception as exc:
        return {"error": str(exc)}
