"""
ROSA OS — Self-improvement API.
POST /api/self-improve/run          — trigger one improvement cycle
GET  /api/self-improve/proposals    — list pending proposals
GET  /api/self-improve/events       — list recent events (filterable by severity)
POST /api/self-improve/{id}/apply   — apply a proposal (requires confirmation)
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.self_improve")
router = APIRouter(prefix="/api/self-improve", tags=["self-improvement"])


class ProposalOut(BaseModel):
    id: str
    filename: str
    summary: str
    created_at: str
    applied: bool


class EventOut(BaseModel):
    id: str
    event_type: str
    description: str
    severity: str
    task_id: str | None
    created_at: str


@router.post("/run")
async def run_improvement_cycle() -> dict:
    """Trigger one self-improvement cycle. Returns a report."""
    try:
        from core.self_improvement.collector import Collector
        from core.self_improvement.analyzer import Analyzer
        from core.self_improvement.patcher import Patcher

        collector = Collector()
        metrics = await collector.collect()

        if not metrics["has_issues"]:
            return {
                "status": "nothing_to_improve",
                "message": "No failures or low-rated tasks found in recent history.",
                "metrics": metrics,
            }

        analyzer = Analyzer()
        analysis = await analyzer.analyze(metrics)

        patcher = Patcher()
        proposal_path = await patcher.write_proposal(analysis)

        return {
            "status": "proposal_created",
            "proposal_file": proposal_path,
            "summary": analysis.get("summary", ""),
            "metrics": metrics,
            "message": (
                f"Improvement proposal written to {proposal_path}. "
                "Review it and call POST /api/self-improve/{id}/apply to apply."
            ),
        }
    except Exception as exc:
        logger.error("Self-improvement cycle failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/events", response_model=list[EventOut])
async def list_events(severity: str | None = None, limit: int = 50) -> list[EventOut]:
    """List recent events, optionally filtered by severity (info/warning/high/critical)."""
    from core.memory.store import get_store
    store = await get_store()
    events = await store.list_events(severity=severity, limit=limit)
    return [
        EventOut(
            id=e.id,
            event_type=e.event_type,
            description=e.description,
            severity=e.severity,
            task_id=e.task_id,
            created_at=e.created_at.isoformat(),
        )
        for e in events
    ]


@router.get("/proposals", response_model=list[ProposalOut])
async def list_proposals() -> list[ProposalOut]:
    """List all pending improvement proposals."""
    from core.self_improvement.patcher import Patcher
    patcher = Patcher()
    return await patcher.list_proposals()


@router.post("/{proposal_id}/apply")
async def apply_proposal(proposal_id: str, confirmed: bool = False) -> dict:
    """
    Apply a proposal to the main system.
    Requires ?confirmed=true to proceed — this is the human-in-the-loop gate.
    """
    if not confirmed:
        return {
            "status": "confirmation_required",
            "message": (
                "To apply this proposal, call this endpoint again with ?confirmed=true. "
                "Read the proposal file in experimental/ before confirming."
            ),
        }

    from core.self_improvement.patcher import Patcher
    patcher = Patcher()
    result = await patcher.apply_proposal(proposal_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return {"status": "applied", "detail": result}
