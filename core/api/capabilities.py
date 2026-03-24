"""ROSA OS — Capabilities API."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


class RecordRequest(BaseModel):
    name: str
    success: bool


@router.get("")
def get_capabilities():
    from core.metacognition.capability_map import get_capability_map
    cap_map = get_capability_map()
    return {"capabilities": cap_map.to_dict(), "summary": cap_map.summary()}


@router.get("/gaps")
def get_gaps():
    from core.metacognition.capability_map import get_capability_map
    gaps = get_capability_map().get_gaps()
    return {"gaps": [g.to_dict() for g in gaps], "count": len(gaps)}


@router.post("/record")
def record_capability(req: RecordRequest):
    from core.metacognition.capability_map import get_capability_map
    cap_map = get_capability_map()
    if req.success:
        cap_map.record_success(req.name)
    else:
        cap_map.record_failure(req.name)
    cap = cap_map.get(req.name)
    return {"name": req.name, "level": cap.level if cap else None}


@router.get("/reflection/recent")
def get_recent_reflections(limit: int = 20):
    from core.metacognition.self_reflection import load_reflections
    return {"reflections": load_reflections(limit=limit)}


@router.get("/gaps/report")
async def get_gap_report():
    from core.metacognition.gap_analyzer import weekly_gap_report
    return await weekly_gap_report(days=7)
