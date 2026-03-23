"""
ROSA OS v3 — Models API.

GET   /api/models            — list all models with metadata
PATCH /api/models/{model_id} — enable/disable a model
GET   /api/models/strategies — list routing strategies
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.router.models_router import get_models_router

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelToggle(BaseModel):
    enabled: bool


@router.get("")
async def list_models():
    """Return all model definitions with enabled/disabled status."""
    return get_models_router().list_models()


@router.patch("/{model_id}")
async def toggle_model(model_id: str, body: ModelToggle):
    """Enable or disable a model by its config key."""
    mr = get_models_router()
    ok = mr.set_enabled(model_id, body.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    return {"model_id": model_id, "enabled": body.enabled}


@router.get("/strategies")
async def list_strategies():
    """Return available routing strategies."""
    return get_models_router().list_strategies()
