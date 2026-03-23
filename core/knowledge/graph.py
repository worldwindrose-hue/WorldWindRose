"""
ROSA OS v3 — Knowledge Graph logic.

Provides three main operations:
- add_insight(text, metadata)  → parse insight into nodes/edges via LLM
- add_from_dialog(turn)        → extract entities/relations from a conversation turn
- query_graph(query, limit)    → search nodes + their edges
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.memory.store import get_store

logger = logging.getLogger("rosa.knowledge.graph")

# ── LLM helpers ─────────────────────────────────────────────────────────────

async def _llm_extract(text: str) -> dict:
    """
    Call Kimi K2.5 (via OpenRouter) to parse text into graph nodes and edges.
    Returns a dict with keys: nodes[], edges[]
    Falls back to a single insight node if the LLM call fails.
    """
    try:
        from core.config import get_settings
        import httpx

        settings = get_settings()
        if not settings.openrouter_api_key:
            raise ValueError("No OPENROUTER_API_KEY — using fallback")

        prompt = (
            "You are a knowledge graph builder. "
            "Parse the following text into a JSON object with this schema:\n"
            '{"nodes": [{"title": str, "type": "insight|entity|concept|fact", "summary": str}], '
            '"edges": [{"from": int, "to": int, "relation": str}]}\n'
            "- nodes[].type must be one of: insight, entity, concept, fact\n"
            "- edges[].from and .to are 0-based indices into the nodes array\n"
            "- relation examples: related_to, part_of, caused_by, depends_on, contradicts\n"
            "- Return ONLY valid JSON, no markdown.\n\n"
            f"Text:\n{text[:4000]}"
        )

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.cloud_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            return json.loads(content)

    except Exception as exc:
        logger.warning("LLM extraction failed (%s) — using fallback single node", exc)
        return {
            "nodes": [{"title": text[:120], "type": "insight", "summary": text[:500]}],
            "edges": [],
        }


# ── Public API ───────────────────────────────────────────────────────────────

async def add_insight(
    text: str,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """
    Parse a free-form insight text into knowledge graph nodes/edges and persist them.
    Returns {"nodes_created": int, "edges_created": int, "nodes": [...]}.
    """
    store = await get_store()
    source_type = (metadata or {}).get("source_type", "manual")

    extracted = await _llm_extract(text)
    raw_nodes = extracted.get("nodes", [])
    raw_edges = extracted.get("edges", [])

    # Create nodes
    created_nodes = []
    for n in raw_nodes:
        node = await store.create_node(
            title=n.get("title", "Untitled")[:256],
            type=n.get("type", "insight"),
            summary=n.get("summary", ""),
            source_type=source_type,
        )
        created_nodes.append(node)

    # Create edges (using indices from LLM response)
    edges_created = 0
    for e in raw_edges:
        fi, ti = e.get("from", -1), e.get("to", -1)
        if 0 <= fi < len(created_nodes) and 0 <= ti < len(created_nodes):
            await store.create_edge(
                from_node_id=created_nodes[fi].id,
                to_node_id=created_nodes[ti].id,
                relation_type=e.get("relation", "related_to"),
            )
            edges_created += 1

    return {
        "nodes_created": len(created_nodes),
        "edges_created": edges_created,
        "nodes": [
            {
                "id": n.id,
                "title": n.title,
                "type": n.type,
                "summary": n.summary,
                "created_at": n.created_at.isoformat(),
            }
            for n in created_nodes
        ],
    }


async def add_from_dialog(turn_content: str, session_id: str | None = None) -> dict:
    """
    Extract entities/concepts from a conversation turn and add to the graph.
    Lighter extraction — asks LLM for only the top 3 most notable entities.
    """
    if len(turn_content) < 50:
        return {"nodes_created": 0, "edges_created": 0, "nodes": []}

    text = (
        "Extract up to 3 important entities, concepts, or facts from this text. "
        "Return JSON: {\"nodes\": [{\"title\": str, \"type\": \"entity|concept|fact\", \"summary\": str}]}\n\n"
        f"Text:\n{turn_content[:2000]}"
    )
    try:
        from core.config import get_settings
        import httpx

        settings = get_settings()
        if not settings.openrouter_api_key:
            return {"nodes_created": 0, "edges_created": 0, "nodes": []}

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.cloud_model,
                    "messages": [{"role": "user", "content": text}],
                    "temperature": 0.1,
                    "max_tokens": 512,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            extracted = json.loads(content)
    except Exception as exc:
        logger.debug("Dialog extraction failed: %s", exc)
        return {"nodes_created": 0, "edges_created": 0, "nodes": []}

    store = await get_store()
    created = []
    for n in extracted.get("nodes", [])[:3]:
        node = await store.create_node(
            title=n.get("title", "")[:256],
            type=n.get("type", "entity"),
            summary=n.get("summary", ""),
            source_type="dialog",
            source_id=session_id,
        )
        created.append(node)

    return {
        "nodes_created": len(created),
        "edges_created": 0,
        "nodes": [{"id": n.id, "title": n.title, "type": n.type} for n in created],
    }


async def query_graph(query: str, limit: int = 10) -> dict:
    """
    Search the knowledge graph by query string.
    Returns matching nodes and all edges touching those nodes.
    """
    store = await get_store()
    nodes = await store.search_nodes(query, limit=limit)
    node_ids = {n.id for n in nodes}

    # Gather edges for found nodes
    all_edges = []
    for node_id in list(node_ids)[:limit]:
        edges = await store.list_edges(node_id=node_id, limit=20)
        all_edges.extend(edges)

    # De-duplicate edges
    seen_edge_ids = set()
    unique_edges = []
    for e in all_edges:
        if e.id not in seen_edge_ids:
            seen_edge_ids.add(e.id)
            unique_edges.append(e)

    # Pull in related nodes not already in result set
    extra_ids = set()
    for e in unique_edges:
        extra_ids.add(e.from_node_id)
        extra_ids.add(e.to_node_id)
    extra_ids -= node_ids

    extra_nodes = []
    for nid in list(extra_ids)[:20]:
        n = await store.get_node(nid)
        if n:
            extra_nodes.append(n)

    all_nodes = list(nodes) + extra_nodes

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
            for n in all_nodes
        ],
        "edges": [
            {
                "id": e.id,
                "from_node_id": e.from_node_id,
                "to_node_id": e.to_node_id,
                "relation_type": e.relation_type,
                "weight": e.weight,
                "created_at": e.created_at.isoformat(),
            }
            for e in unique_edges
        ],
    }
