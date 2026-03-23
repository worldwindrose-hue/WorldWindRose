"""Async tests for the MemoryStore."""

import sys
import pytest
import pytest_asyncio
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


@pytest.mark.asyncio
async def test_save_and_list_turns():
    from core.memory.store import get_store
    store = await get_store()
    await store.save_turn("user", "hello", session_id="s1")
    await store.save_turn("assistant", "hi", model_used="kimi", session_id="s1")
    turns = await store.list_turns(session_id="s1")
    assert len(turns) == 2


@pytest.mark.asyncio
async def test_save_and_update_task():
    from core.memory.store import get_store
    store = await get_store()
    task = await store.save_task("Do something", plan="Step 1")
    assert task.status == "pending"

    updated = await store.update_task(task.id, status="done", owner_rating=5)
    assert updated.status == "done"
    assert updated.owner_rating == 5


@pytest.mark.asyncio
async def test_failed_tasks():
    from core.memory.store import get_store
    store = await get_store()
    t1 = await store.save_task("Task A")
    await store.update_task(t1.id, status="failed")
    t2 = await store.save_task("Task B")
    await store.update_task(t2.id, status="done")

    failed = await store.get_failed_tasks()
    assert len(failed) == 1
    assert failed[0].id == t1.id


@pytest.mark.asyncio
async def test_low_rated_tasks():
    from core.memory.store import get_store
    store = await get_store()
    t1 = await store.save_task("Bad task")
    await store.update_task(t1.id, owner_rating=1)
    t2 = await store.save_task("Good task")
    await store.update_task(t2.id, owner_rating=5)

    low = await store.get_low_rated_tasks(max_rating=2)
    assert len(low) == 1
    assert low[0].id == t1.id


@pytest.mark.asyncio
async def test_save_and_get_reflection():
    from core.memory.store import get_store
    store = await get_store()
    r = await store.save_reflection("Improved routing logic", suggestions="- Adjust thresholds")
    assert r.applied is False

    reflections = await store.get_recent_reflections()
    assert len(reflections) == 1

    marked = await store.mark_reflection_applied(r.id)
    assert marked.applied is True


@pytest.mark.asyncio
async def test_save_and_get_event():
    from core.memory.store import get_store
    store = await get_store()
    e = await store.save_event("error", "API timeout", severity="high")
    events = await store.get_high_severity_events()
    assert len(events) == 1
    assert events[0].id == e.id
