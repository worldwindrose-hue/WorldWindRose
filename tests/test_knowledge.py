"""
Tests for ROSA OS v3 — Knowledge Graph (store CRUD + API endpoints).
"""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
async def reset_store():
    """Use a fresh in-memory DB for each test."""
    import core.memory.store as store_mod
    store_mod._engine = None
    store_mod._session_factory = None
    store_mod._store_instance = None
    await store_mod.init_db(":memory:")
    yield
    store_mod._engine = None
    store_mod._session_factory = None
    store_mod._store_instance = None


# ── Store tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_nodes():
    from core.memory.store import get_store
    store = await get_store()

    n1 = await store.create_node(title="Граф знаний", type="concept", summary="Структура для хранения знаний")
    n2 = await store.create_node(title="Kimi K2.5", type="entity", summary="Языковая модель")

    nodes = await store.list_nodes()
    assert len(nodes) == 2
    ids = {n.id for n in nodes}
    assert n1.id in ids
    assert n2.id in ids


@pytest.mark.asyncio
async def test_list_nodes_by_type():
    from core.memory.store import get_store
    store = await get_store()

    await store.create_node(title="Insight 1", type="insight")
    await store.create_node(title="Entity 1", type="entity")
    await store.create_node(title="Insight 2", type="insight")

    insights = await store.list_nodes(type="insight")
    assert len(insights) == 2
    assert all(n.type == "insight" for n in insights)


@pytest.mark.asyncio
async def test_search_nodes():
    from core.memory.store import get_store
    store = await get_store()

    await store.create_node(title="Машинное обучение", summary="Методы ML для Rosa")
    await store.create_node(title="Python", summary="Язык программирования")
    await store.create_node(title="Нейронные сети", summary="Основа ML методов")

    results = await store.search_nodes("ML")
    assert len(results) >= 1
    # "ML" appears in the summary of first node
    assert any("ML" in (n.summary or "") for n in results)


@pytest.mark.asyncio
async def test_create_and_list_edges():
    from core.memory.store import get_store
    store = await get_store()

    n1 = await store.create_node(title="Концепция A", type="concept")
    n2 = await store.create_node(title="Концепция B", type="concept")
    edge = await store.create_edge(n1.id, n2.id, relation_type="related_to", weight=0.8)

    assert edge.from_node_id == n1.id
    assert edge.to_node_id == n2.id
    assert edge.relation_type == "related_to"
    assert abs(edge.weight - 0.8) < 0.001

    # List edges for n1
    edges = await store.list_edges(node_id=n1.id)
    assert len(edges) == 1
    assert edges[0].id == edge.id

    # List edges for n2 (also found because direction includes both sides)
    edges_b = await store.list_edges(node_id=n2.id)
    assert len(edges_b) == 1


@pytest.mark.asyncio
async def test_get_node():
    from core.memory.store import get_store
    store = await get_store()

    n = await store.create_node(title="Тест", type="fact", summary="Тестовый факт")
    fetched = await store.get_node(n.id)
    assert fetched is not None
    assert fetched.title == "Тест"
    assert fetched.type == "fact"


# ── API tests ────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from httpx import AsyncClient, ASGITransport
    from core.app import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_knowledge_list_nodes_empty(client):
    async with client as c:
        resp = await c.get("/api/knowledge/nodes")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_knowledge_graph_no_query(client):
    async with client as c:
        resp = await c.get("/api/knowledge/graph")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "edges" in data
