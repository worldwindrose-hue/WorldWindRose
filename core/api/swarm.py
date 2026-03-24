"""
ROSA OS — Auto-Scaling Swarm API (Phase 8).

POST /api/swarm/auto    {task, context, max_agents}
GET  /api/swarm/roles
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.swarm")
router = APIRouter(prefix="/api/swarm", tags=["swarm"])


class AutoSwarmRequest(BaseModel):
    task: str
    context: str = ""
    max_agents: int | None = None


@router.post("/auto")
async def auto_swarm(req: AutoSwarmRequest):
    from core.swarm.auto_scaler import auto_run
    return await auto_run(req.task, req.context, req.max_agents)


@router.get("/roles")
async def list_roles():
    from core.swarm.auto_scaler import _AGENT_SYSTEM_PROMPTS
    return {"roles": list(_AGENT_SYSTEM_PROMPTS.keys())}


@router.post("/complexity")
async def classify_complexity(req: AutoSwarmRequest):
    from core.swarm.auto_scaler import classify_complexity, decide_agent_count, decide_agent_roles
    count = decide_agent_count(req.task)
    complexity = classify_complexity(req.task)
    roles = decide_agent_roles(req.task, count)
    return {"task": req.task, "complexity": complexity, "agent_count": count, "roles": roles}
