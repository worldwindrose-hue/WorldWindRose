"""
ROSA OS — PAL (Program-Aided Learning) API.
Solves math/logic problems by generating and executing Python code.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/pal", tags=["pal"])


class PALRequest(BaseModel):
    question: str


@router.post("/solve", response_model=dict)
async def solve(req: PALRequest) -> dict:
    from core.reasoning.pal import solve as do_solve
    return await do_solve(req.question)


@router.post("/check", response_model=dict)
async def check_math(req: PALRequest) -> dict:
    """Check if a query is suitable for PAL (math/logic detection)."""
    from core.reasoning.pal import is_math_query
    return {"question": req.question, "is_math": is_math_query(req.question)}
