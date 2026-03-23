"""
Tests for ROSA OS v3 — Skills & SkillProgress (store CRUD + API endpoints).
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
async def test_create_and_list_skills():
    from core.memory.store import get_store
    store = await get_store()

    s1 = await store.create_skill("coding", "Навыки программирования")
    s2 = await store.create_skill("parsing", "Парсинг данных")

    skills = await store.list_skills()
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert "coding" in names
    assert "parsing" in names


@pytest.mark.asyncio
async def test_get_skill_by_name():
    from core.memory.store import get_store
    store = await get_store()

    await store.create_skill("business_planning", "Бизнес-планирование")
    found = await store.get_skill_by_name("business_planning")
    assert found is not None
    assert found.name == "business_planning"

    not_found = await store.get_skill_by_name("nonexistent")
    assert not_found is None


@pytest.mark.asyncio
async def test_save_and_get_skill_progress():
    from core.memory.store import get_store
    store = await get_store()

    skill = await store.create_skill("russian_nlp", "Русскоязычные NLP задачи")

    p1 = await store.save_skill_progress(skill.id, level=2.0, goal=5.0, notes="Начальный уровень", assessed_by="owner")
    p2 = await store.save_skill_progress(skill.id, level=3.5, goal=5.0, notes="Прогресс после тренировки", assessed_by="auto")

    history = await store.get_skill_history(skill.id)
    assert len(history) == 2

    latest = await store.get_latest_skill_progress(skill.id)
    assert latest is not None
    # Latest should be the most recently assessed (p2)
    assert abs(latest.level - 3.5) < 0.001


@pytest.mark.asyncio
async def test_skill_progress_empty_history():
    from core.memory.store import get_store
    store = await get_store()

    skill = await store.create_skill("vision", "Работа с изображениями")
    latest = await store.get_latest_skill_progress(skill.id)
    assert latest is None


# ── API tests ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client():
    from httpx import AsyncClient, ASGITransport
    from core.app import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_skills_empty(client):
    async with client as c:
        resp = await c.get("/api/self-improve/skills")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_skill_api(client):
    async with client as c:
        resp = await c.post(
            "/api/self-improve/skills",
            json={"name": "coding", "description": "Навыки программирования"},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "coding"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_duplicate_skill_api(client):
    async with client as c:
        await c.post("/api/self-improve/skills", json={"name": "coding"})
        resp = await c.post("/api/self-improve/skills", json={"name": "coding"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_assess_skill_api(client):
    async with client as c:
        create_resp = await c.post("/api/self-improve/skills", json={"name": "coding"})
        skill_id = create_resp.json()["id"]

        assess_resp = await c.post(
            f"/api/self-improve/skills/{skill_id}/assess",
            json={"level": 3.0, "goal": 5.0, "notes": "Хороший прогресс"},
        )
    assert assess_resp.status_code == 201
    data = assess_resp.json()
    assert abs(data["level"] - 3.0) < 0.001
    assert data["skill_id"] == skill_id


@pytest.mark.asyncio
async def test_list_skills_with_progress(client):
    async with client as c:
        cr = await c.post("/api/self-improve/skills", json={"name": "reasoning"})
        sid = cr.json()["id"]
        await c.post(f"/api/self-improve/skills/{sid}/assess", json={"level": 4.0, "goal": 5.0})

        resp = await c.get("/api/self-improve/skills")
    assert resp.status_code == 200
    skills = resp.json()
    assert len(skills) == 1
    assert abs(skills[0]["latest_level"] - 4.0) < 0.001
