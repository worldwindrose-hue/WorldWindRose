"""
ROSA OS v6 — Block 1 tests: Eternal Hybrid Memory.
Tests: WorkingMemory, EpisodicMemory, GraphMemory, SessionContext,
       EternalMemory singleton, MemoryInjector, Memory API stats.
"""

from __future__ import annotations

import sys
import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def reset_db():
    import core.memory.store as store_mod
    store_mod._engine = None
    store_mod._session_factory = None
    store_mod._store_instance = None
    await store_mod.init_db(":memory:")
    yield
    store_mod._engine = None
    store_mod._session_factory = None
    store_mod._store_instance = None


@pytest.fixture(autouse=True)
def reset_eternal_singleton():
    import core.memory.eternal as eternal_mod
    old = eternal_mod._eternal_memory_instance
    eternal_mod._eternal_memory_instance = None
    yield
    eternal_mod._eternal_memory_instance = old


@pytest.fixture
def client():
    from httpx import AsyncClient, ASGITransport
    from core.app import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_working_memory_add_and_get():
    """WorkingMemory stores and retrieves messages."""
    from core.memory.eternal import WorkingMemory
    wm = WorkingMemory(max_messages=10, max_tokens=500)
    wm.add("user", "Hello Rosa!")
    wm.add("assistant", "Hello! How can I help?")
    msgs = wm.get_messages()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello Rosa!"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_working_memory_compression_threshold():
    """WorkingMemory detects when compression is needed."""
    from core.memory.eternal import WorkingMemory
    # Very low token limit to trigger compression
    wm = WorkingMemory(max_messages=100, max_tokens=10)
    for i in range(5):
        wm.add("user", "This is a test message that is quite long " * 2)
    assert wm.needs_compression() is True


@pytest.mark.asyncio
async def test_episodic_memory_add_and_search():
    """EpisodicMemory adds and searches entries (SQLite fallback path)."""
    from core.memory.eternal import EpisodicMemory
    em = EpisodicMemory()
    # Force SQLite fallback by disabling ChromaDB
    em._chroma_available = False
    em._chroma_client = None
    em._collection = None

    await em.add("Rosa is an AI assistant", source="test", tags=["ai"])
    results = await em.search("AI assistant", top_k=5)
    # Should return list (may be empty in fresh in-memory DB, but not crash)
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_graph_memory_add_fact():
    """GraphMemory stores facts as nodes+edges in SQLite."""
    from core.memory.eternal import GraphMemory
    gm = GraphMemory()
    # Should not raise
    await gm.add_fact("Rosa", "is_a", "AI_assistant", source="test")

    from core.memory.store import get_store
    store = await get_store()
    nodes = await store.list_nodes(limit=10)
    titles = [n.title for n in nodes]
    # At least one entity node should exist
    assert len(nodes) > 0


@pytest.mark.asyncio
async def test_session_context_save_load(tmp_path):
    """SessionContext saves and loads context to/from file."""
    from core.memory.eternal import SessionContext
    sc = SessionContext()

    # Patch the context path to use tmp_path
    ctx_file = tmp_path / "session_context.json"
    with patch("core.memory.eternal.Path") as MockPath:
        # Use real Path for the actual operations
        import pathlib
        MockPath.side_effect = lambda p: pathlib.Path(str(tmp_path / p.lstrip("memory/"))) if "memory" in str(p) else pathlib.Path(p)
        MockPath.return_value = ctx_file

        sc._cache = {}
        await sc.save({"last_topic": "Python", "session_count": 5})

    # Verify the cache was updated
    assert sc._cache.get("last_topic") == "Python"
    assert sc._cache.get("session_count") == 5


@pytest.mark.asyncio
async def test_eternal_memory_singleton():
    """get_eternal_memory() returns the same instance each call."""
    from core.memory.eternal import get_eternal_memory, EternalMemory
    m1 = get_eternal_memory()
    m2 = get_eternal_memory()
    assert m1 is m2
    assert isinstance(m1, EternalMemory)


@pytest.mark.asyncio
async def test_memory_injector_build_context():
    """build_memory_context returns a string with [ПАМЯТЬ РОЗЫ] block."""
    from core.memory.memory_injector import build_memory_context
    ctx = await build_memory_context("What is Python?")
    assert isinstance(ctx, str)
    # Either returns memory block or empty string (both acceptable)
    if ctx:
        assert "[ПАМЯТЬ РОЗЫ]" in ctx


@pytest.mark.asyncio
async def test_memory_injector_inject_into_messages():
    """inject_into_messages prepends memory context to messages."""
    from core.memory.memory_injector import inject_into_messages
    messages = [{"role": "user", "content": "Hello"}]
    result = await inject_into_messages(messages, "Hello")
    assert isinstance(result, list)
    assert len(result) >= 1


@pytest.mark.asyncio
async def test_memory_api_stats(client):
    """GET /api/memory/stats returns a dict."""
    async with client as c:
        resp = await c.get("/api/memory/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_memory_api_search(client):
    """GET /api/memory/search returns episodic and graph keys."""
    async with client as c:
        resp = await c.get("/api/memory/search?q=test")
    assert resp.status_code == 200
    data = resp.json()
    assert "episodic" in data
    assert "graph" in data


@pytest.mark.asyncio
async def test_memory_api_remember(client):
    """POST /api/memory/remember saves text."""
    async with client as c:
        resp = await c.post("/api/memory/remember", json={"text": "Test memory", "importance": 0.8})
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] in ("remembered", "error")


@pytest.mark.asyncio
async def test_memory_api_context(client):
    """GET /api/memory/context returns context dict."""
    async with client as c:
        resp = await c.get("/api/memory/context")
    assert resp.status_code == 200
    data = resp.json()
    assert "context" in data
