"""Integration tests for ROSA OS API endpoints."""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
async def reset_db():
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


@pytest.fixture
def client():
    from httpx import AsyncClient, ASGITransport
    from core.app import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_health(client):
    async with client as c:
        r = await c.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_and_list_tasks(client):
    async with client as c:
        create_r = await c.post(
            "/api/tasks",
            json={"description": "Test task"},
        )
        assert create_r.status_code == 201
        task = create_r.json()
        assert task["description"] == "Test task"
        assert task["status"] == "pending"

        list_r = await c.get("/api/tasks")
        assert list_r.status_code == 200
        tasks = list_r.json()
        assert any(t["id"] == task["id"] for t in tasks)


@pytest.mark.asyncio
async def test_update_task(client):
    async with client as c:
        create_r = await c.post("/api/tasks", json={"description": "Update me"})
        task_id = create_r.json()["id"]

        patch_r = await c.patch(
            f"/api/tasks/{task_id}",
            json={"status": "done", "owner_rating": 4},
        )
        assert patch_r.status_code == 200
        updated = patch_r.json()
        assert updated["status"] == "done"
        assert updated["owner_rating"] == 4


@pytest.mark.asyncio
async def test_update_task_not_found(client):
    async with client as c:
        r = await c.patch("/api/tasks/nonexistent", json={"status": "done"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_memory_reflections_empty(client):
    async with client as c:
        r = await c.get("/api/memory/reflections")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_store_event(client):
    async with client as c:
        r = await c.post(
            "/api/memory/events",
            json={"event_type": "error", "description": "Test error", "severity": "high"},
        )
    assert r.status_code == 201
    assert "id" in r.json()
