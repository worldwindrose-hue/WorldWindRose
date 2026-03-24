"""
ROSA OS — Metacognition API.
Exposes response quality scores and statistics.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/metacognition", tags=["metacognition"])


class QualityOut(BaseModel):
    id: str
    session_id: str
    message: str
    completeness: float
    accuracy: float
    helpfulness: float
    overall: float
    weak_points: list[str]
    improvement_hint: str | None
    assessed_at: str

    @classmethod
    def from_orm(cls, rq) -> "QualityOut":
        import json
        wp: list[str] = []
        if rq.weak_points:
            try:
                wp = json.loads(rq.weak_points)
            except Exception:
                wp = [rq.weak_points]
        return cls(
            id=rq.id,
            session_id=rq.session_id,
            message=rq.message[:200],
            completeness=rq.completeness,
            accuracy=rq.accuracy,
            helpfulness=rq.helpfulness,
            overall=rq.overall,
            weak_points=wp,
            improvement_hint=rq.improvement_hint,
            assessed_at=rq.assessed_at.isoformat(),
        )


@router.get("/quality", response_model=list[QualityOut])
async def list_quality(
    session_id: str | None = None,
    limit: int = 20,
) -> list[QualityOut]:
    """Return recent response quality assessments."""
    from core.memory.store import get_store
    store = await get_store()
    records = await store.list_quality(session_id=session_id, limit=min(limit, 100))
    return [QualityOut.from_orm(r) for r in records]


@router.get("/stats")
async def quality_stats() -> dict[str, Any]:
    """Return aggregate quality statistics and top weak points."""
    from core.memory.store import get_store
    store = await get_store()
    return await store.get_quality_stats()
