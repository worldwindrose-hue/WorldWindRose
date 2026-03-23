"""
ROSA OS v3 — Knowledge Graph API.

POST /api/knowledge/insights  — add insight text, parse into nodes/edges
GET  /api/knowledge/graph     — search subgraph by query
GET  /api/knowledge/nodes     — list nodes (filterable by type)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.knowledge.graph import add_insight, query_graph
from core.memory.store import get_store

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class InsightIn(BaseModel):
    text: str
    metadata: dict[str, Any] | None = None


class InsightOut(BaseModel):
    nodes_created: int
    edges_created: int
    nodes: list[dict]


class NodeOut(BaseModel):
    id: str
    type: str
    title: str
    summary: str | None
    source_type: str
    source_id: str | None
    created_at: datetime
    updated_at: datetime


class EdgeOut(BaseModel):
    id: str
    from_node_id: str
    to_node_id: str
    relation_type: str
    weight: float
    created_at: datetime


class GraphOut(BaseModel):
    nodes: list[dict]
    edges: list[dict]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/insights", response_model=InsightOut, status_code=201)
async def create_insight(body: InsightIn):
    """Parse free-form insight text into knowledge graph nodes/edges and persist."""
    if not body.text.strip():
        raise HTTPException(status_code=422, detail="text cannot be empty")
    result = await add_insight(body.text, body.metadata)
    return result


@router.get("/graph", response_model=GraphOut)
async def get_graph(
    query: str = Query(default="", description="Search query to filter nodes"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return a knowledge subgraph matching the query."""
    if not query.strip():
        # Return recent nodes when no query given
        store = await get_store()
        nodes = await store.list_nodes(limit=limit)
        return {
            "nodes": [
                {
                    "id": n.id,
                    "title": n.title,
                    "type": n.type,
                    "summary": n.summary or "",
                    "source_type": n.source_type,
                    "created_at": n.created_at.isoformat(),
                    "updated_at": n.updated_at.isoformat(),
                }
                for n in nodes
            ],
            "edges": [],
        }
    return await query_graph(query, limit=limit)


@router.get("/nodes", response_model=list[NodeOut])
async def list_nodes(
    type: str | None = Query(default=None, description="Filter by node type: insight|entity|concept|fact"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """List knowledge nodes, optionally filtered by type."""
    store = await get_store()
    nodes = await store.list_nodes(type=type, limit=limit)
    return [
        NodeOut(
            id=n.id,
            type=n.type,
            title=n.title,
            summary=n.summary,
            source_type=n.source_type,
            source_id=n.source_id,
            created_at=n.created_at,
            updated_at=n.updated_at,
        )
        for n in nodes
    ]
