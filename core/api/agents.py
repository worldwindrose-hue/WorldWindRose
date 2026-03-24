"""
ROSA OS — Agents API.
Endpoints for researcher, content pipeline, and swarm agents.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents", tags=["agents"])


class ResearchRequest(BaseModel):
    question: str
    session_id: str = "research"


class ContentRequest(BaseModel):
    topic: str
    content_type: str = "blog_post"
    audience: str = "широкая аудитория"
    research: bool = True


class SwarmRequest(BaseModel):
    task: str
    roles: list[str] | None = None
    context: str = ""


class SocialRequest(BaseModel):
    topic: str
    platforms: list[str] | None = None


@router.post("/research", response_model=dict)
async def research(req: ResearchRequest) -> dict:
    from core.agents.researcher import research as do_research
    return await do_research(req.question, session_id=req.session_id)


@router.post("/content", response_model=dict)
async def create_content(req: ContentRequest) -> dict:
    from core.agents.content_pipeline import create_content as do_content
    return await do_content(
        topic=req.topic,
        content_type=req.content_type,
        audience=req.audience,
        research=req.research,
    )


@router.post("/content/social", response_model=dict)
async def social_posts(req: SocialRequest) -> dict:
    from core.agents.content_pipeline import generate_social_posts
    return await generate_social_posts(req.topic, req.platforms)


@router.post("/swarm", response_model=dict)
async def run_swarm(req: SwarmRequest) -> dict:
    from core.agents.swarm import run_swarm as do_swarm
    return await do_swarm(task=req.task, roles=req.roles, context=req.context)


@router.get("/list", response_model=list)
async def list_agents() -> list:
    from core.agents.factory import get_factory
    return get_factory().list_agents()
