"""
ROSA OS — Self-improvement API.
POST /api/self-improve/run          — trigger one improvement cycle
GET  /api/self-improve/proposals    — list pending proposals
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
