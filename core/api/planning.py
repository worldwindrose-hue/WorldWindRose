"""
ROSA OS — Mission Planning API (Phase 10).

POST /api/planning/missions          {message} → create mission
GET  /api/planning/missions          → list all missions
GET  /api/planning/missions/{id}     → get mission
POST /api/planning/missions/{id}/approve  {step_ids} → approve
POST /api/planning/missions/{id}/execute → execute
POST /api/planning/missions/{id}/cancel  → cancel
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.planning")
router = APIRouter(prefix="/api/planning", tags=["planning"])


class CreateMissionRequest(BaseModel):
    message: str


class ApproveRequest(BaseModel):
    step_ids: list[int] | None = None  # None = approve all


@router.post("/missions")
async def create_mission(req: CreateMissionRequest):
    from core.planning.mission_planner import parse_intent
    mission = await parse_intent(req.message)
    return mission.to_dict()


@router.get("/missions")
async def list_missions():
    from core.planning.mission_planner import list_missions
    return list_missions()


@router.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    from core.planning.mission_planner import get_mission
    m = get_mission(mission_id)
    if not m:
        raise HTTPException(404, "Mission not found")
    return m.to_dict()


@router.post("/missions/{mission_id}/approve")
async def approve_mission(mission_id: str, req: ApproveRequest = ApproveRequest()):
    from core.planning.mission_planner import approve_mission
    try:
        mission = await approve_mission(mission_id, req.step_ids)
        return mission.to_dict()
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/missions/{mission_id}/execute")
async def execute_mission(mission_id: str):
    from core.planning.mission_planner import execute_mission
    try:
        mission = await execute_mission(mission_id)
        return mission.to_dict()
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    from core.planning.mission_planner import cancel_mission
    ok = cancel_mission(mission_id)
    if not ok:
        raise HTTPException(404, "Mission not found")
    return {"cancelled": True, "mission_id": mission_id}
