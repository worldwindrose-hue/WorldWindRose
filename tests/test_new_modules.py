"""
ROSA OS v4 — Tests for new modules (Phases 3-10).
Tests: safety sandbox, prediction, vision, agents, projects, metacognition.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ── PHASE 3: Safety Sandbox ────────────────────────────────────────────────────

class TestFirewall:
    def test_safe_command_allowed(self):
        from core.security.firewall import is_safe_command
        assert is_safe_command("python3 tests/test_api.py")

    def test_dangerous_rm_blocked(self):
        from core.security.firewall import check_command, FirewallBlock
        with pytest.raises(FirewallBlock):
            check_command("rm -rf /")

    def test_dangerous_sudo_blocked(self):
        from core.security.firewall import check_command, FirewallBlock
        with pytest.raises(FirewallBlock):
            check_command("sudo chmod 777 /etc/passwd")

    def test_pytest_is_whitelisted(self):
        from core.security.firewall import is_safe_command
        assert is_safe_command("pytest tests/")

    def test_check_text_safe(self):
        from core.security.firewall import check_text
        # Should not raise for safe text
        check_text("def hello(): print('world')")

    def test_check_text_dangerous(self):
        from core.security.firewall import check_text, FirewallBlock
        with pytest.raises(FirewallBlock):
            check_text("import os; os.system('rm -rf /')")


class TestSafetySandbox:
    def test_write_patch_to_sandbox(self, tmp_path):
        from core.self_improvement import safety
        # Override sandbox dir for testing
        original_dir = safety.SANDBOX_DIR
        safety.SANDBOX_DIR = tmp_path / "patches"
        safety.SANDBOX_DIR.mkdir(parents=True)

        pid, path = safety.write_patch_to_sandbox("test_patch.py", "# test code", "testid")
        assert pid == "testid"
        assert path.exists()
        assert path.read_text() == "# test code"

        safety.SANDBOX_DIR = original_dir

    def test_rollback_patch(self, tmp_path):
        from core.self_improvement import safety
        # Setup
        sandbox_dir = tmp_path / "patches"
        rejected_dir = tmp_path / "rejected"
        sandbox_dir.mkdir(parents=True)
        rejected_dir.mkdir(parents=True)
        original_sandbox = safety.SANDBOX_DIR
        original_rejected = safety.REJECTED_DIR
        safety.SANDBOX_DIR = sandbox_dir
        safety.REJECTED_DIR = rejected_dir

        # Create a patch
        patch_dir = sandbox_dir / "pid123"
        patch_dir.mkdir()
        (patch_dir / "patch.py").write_text("# code")

        safety.rollback_patch("pid123")
        assert not patch_dir.exists()
        assert (rejected_dir / "pid123").exists()

        safety.SANDBOX_DIR = original_sandbox
        safety.REJECTED_DIR = original_rejected

    def test_list_pending_patches(self, tmp_path):
        from core.self_improvement import safety
        original_dir = safety.SANDBOX_DIR
        safety.SANDBOX_DIR = tmp_path / "patches"
        safety.SANDBOX_DIR.mkdir(parents=True)
        (safety.SANDBOX_DIR / "p001").mkdir()
        (safety.SANDBOX_DIR / "p001" / "f.py").write_text("x=1")

        patches = safety.list_pending_patches()
        assert len(patches) == 1
        assert patches[0]["patch_id"] == "p001"

        safety.SANDBOX_DIR = original_dir


# ── PHASE 3: PAL ──────────────────────────────────────────────────────────────

class TestPAL:
    def test_is_math_query_true(self):
        from core.reasoning.pal import is_math_query
        assert is_math_query("Сколько будет 2 + 2?")
        assert is_math_query("Calculate 15% of 200")
        assert is_math_query("Solve for x: 2x = 10")

    def test_is_math_query_false(self):
        from core.reasoning.pal import is_math_query
        assert not is_math_query("Привет как дела?")
        assert not is_math_query("Tell me about Python")

    def test_run_code_safe(self):
        from core.reasoning.pal import run_code
        success, output = run_code("print(2 + 2)")
        assert success
        assert "4" in output

    def test_run_code_timeout(self):
        from core.reasoning.pal import run_code
        success, output = run_code("import time; time.sleep(999)", timeout=1)
        # Should fail due to timeout
        assert not success

    def test_run_code_dangerous_blocked(self):
        from core.reasoning.pal import run_code
        success, output = run_code("import os; os.system('rm -rf /')")
        # Should be blocked by firewall
        assert not success


# ── PHASE 3: Holographic Memory ───────────────────────────────────────────────

class TestHolographicMemory:
    def test_encode_context(self):
        from core.memory.holographic import HolographicStore
        store = HolographicStore(dim=64)
        vec = store.encode_context(["hello world", "test message"])
        assert vec.shape == (64,)
        import numpy as np
        assert abs(np.linalg.norm(vec) - 1.0) < 0.01  # unit vector

    def test_store_and_find_similar(self):
        from core.memory.holographic import HolographicStore
        store = HolographicStore(dim=64)
        store.store_session("s1", ["python code debug"])
        store.store_session("s2", ["cooking recipe pasta"])
        store.store_session("s3", ["python programming tutorial"])

        # Query about Python should be closer to s1/s3
        results = store.find_similar(["python help"], top_k=2)
        assert len(results) == 2
        assert results[0]["similarity"] >= results[1]["similarity"]

    def test_decode_context_empty(self):
        from core.memory.holographic import HolographicStore
        import numpy as np
        store = HolographicStore(dim=64)
        result = store.decode_context(np.zeros(64))
        assert "No stored" in result

    def test_lru_eviction(self):
        from core.memory.holographic import HolographicStore
        store = HolographicStore(dim=32, cache_size=3)
        for i in range(5):
            store.store_session(f"s{i}", [f"message {i}"])
        # Only last 3 should remain
        assert store.stats()["stored_sessions"] == 3

    def test_stats(self):
        from core.memory.holographic import HolographicStore
        store = HolographicStore(dim=64)
        store.store_session("s1", ["hello"])
        stats = store.stats()
        assert stats["stored_sessions"] == 1
        assert stats["vector_dim"] == 64


# ── PHASE 4: Habit Graph ──────────────────────────────────────────────────────

class TestHabitGraph:
    def test_record_and_predict(self):
        from core.prediction.habit_graph import HabitGraph
        graph = HabitGraph()
        for _ in range(5):
            graph.record("code", hour=10, day_of_week=1)
        graph.record("math", hour=14, day_of_week=1)

        predictions = graph.predict_next_task(10, 1)
        assert len(predictions) > 0
        assert predictions[0]["task_type"] == "code"

    def test_top_hours(self):
        from core.prediction.habit_graph import HabitGraph
        graph = HabitGraph()
        graph.record("writing", hour=9, day_of_week=0)
        graph.record("writing", hour=9, day_of_week=0)
        graph.record("writing", hour=14, day_of_week=0)

        top = graph.top_hours_for("writing")
        assert top[0][0] == 9  # hour 9 is most frequent

    def test_summary(self):
        from core.prediction.habit_graph import HabitGraph
        graph = HabitGraph()
        graph.record("code", 10, 1)
        s = graph.summary()
        assert s["total_events"] == 1
        assert s["task_types"] == 1

    def test_serialization(self):
        from core.prediction.habit_graph import HabitGraph
        graph = HabitGraph()
        graph.record("research", 15, 3)
        data = graph.to_dict()
        restored = HabitGraph.from_dict(data)
        assert restored.summary()["total_events"] == 1


# ── PHASE 4: Active Inference ─────────────────────────────────────────────────

class TestActiveInference:
    def test_initial_uniform_belief(self):
        from core.prediction.active_inference import BeliefState
        bs = BeliefState(topics=["a", "b", "c"])
        beliefs = bs.top_beliefs(3)
        # All equal initially
        assert abs(beliefs[0][1] - beliefs[2][1]) < 0.01

    def test_update_increases_belief(self):
        from core.prediction.active_inference import BeliefState
        bs = BeliefState(topics=["code", "math"])
        for _ in range(5):
            bs.update("code")
        top = bs.top_beliefs(1)
        assert top[0][0] == "code"

    def test_surprise_high_for_unexpected(self):
        from core.prediction.active_inference import BeliefState
        import math
        bs = BeliefState(topics=["a", "b"])
        for _ in range(10):
            bs.update("a")
        # "b" should have high surprise now
        surprise_b = bs.surprise("b")
        surprise_a = bs.surprise("a")
        assert surprise_b > surprise_a

    def test_free_energy_decreases_with_updates(self):
        from core.prediction.active_inference import BeliefState
        bs = BeliefState(topics=["a", "b", "c"])
        fe_before = bs.free_energy()
        for _ in range(20):
            bs.update("a")
        fe_after = bs.free_energy()
        assert fe_after < fe_before

    def test_observe_function(self):
        from core.prediction.active_inference import observe
        result = observe("напиши код на Python")
        assert "observed_topic" in result
        assert result["observed_topic"] == "code"

    def test_classify_topic(self):
        from core.prediction.active_inference import _classify_topic
        assert _classify_topic("calculate 2+2") == "math"
        assert _classify_topic("поиск информации") == "research"


# ── PHASE 5: PDF Reader ───────────────────────────────────────────────────────

class TestPDFReader:
    def test_read_nonexistent_file(self):
        from core.integrations.vision.pdf_reader import read_pdf
        result = read_pdf("/nonexistent/file.pdf")
        assert not result["success"]
        assert "not found" in result["error"]

    def test_chunk_text(self):
        from core.integrations.vision.pdf_reader import _chunk_text
        text = "a" * 3000
        chunks = _chunk_text(text, chunk_size=1000, overlap=100)
        assert len(chunks) >= 3
        # Each chunk should be ≤ chunk_size
        for c in chunks:
            assert len(c) <= 1000

    def test_index_directory(self, tmp_path):
        from core.integrations.vision.pdf_reader import index_directory
        # Create fake PDF files
        (tmp_path / "doc1.pdf").write_bytes(b"fake pdf")
        (tmp_path / "doc2.pdf").write_bytes(b"fake pdf 2")

        result = index_directory(tmp_path)
        assert len(result) == 2


# ── PHASE 5: Camera ───────────────────────────────────────────────────────────

class TestCamera:
    def test_is_available_without_cv2(self):
        from core.integrations.vision.camera import is_available
        # May or may not be available — just check it returns bool
        assert isinstance(is_available(), bool)

    def test_capture_frame_no_cv2(self):
        from core.integrations.vision.camera import capture_frame
        # If cv2 not available, should return error dict gracefully
        result = capture_frame(0)
        assert isinstance(result, dict)
        assert "success" in result


# ── PHASE 6: Ensemble Router ──────────────────────────────────────────────────

class TestModelsRouter:
    def test_get_model_for_task(self, tmp_path):
        import yaml
        from core.router.models_router import ModelsRouter

        config = {
            "models": {
                "kimi": {"model_id": "kimi-k2", "enabled": True, "task_affinity": ["CODE"]},
                "local": {"model_id": "llama3", "enabled": True, "task_affinity": ["PRIVATE_FILE"]},
            },
            "routing_strategies": {},
        }
        cfg_path = tmp_path / "models.yaml"
        cfg_path.write_text(yaml.dump(config))
        router = ModelsRouter(config_path=cfg_path)

        assert router.get_model_for_task("CODE") == "kimi-k2"
        assert router.get_model_for_task("PRIVATE_FILE") == "llama3"

    def test_list_strategies_includes_ensemble(self):
        from core.router.models_router import ModelsRouter
        router = ModelsRouter()
        strategies = {s["id"] for s in router.list_strategies()}
        assert "ensemble" in strategies
        assert "task_routing" in strategies


# ── PHASE 7: Projects ─────────────────────────────────────────────────────────

@pytest.fixture
async def memory_store():
    """In-memory store for testing."""
    import os
    os.environ["ROSA_DB_PATH"] = ":memory:"
    from core.memory.store import init_db, get_store
    import core.memory.store as store_module
    store_module._store = None  # reset singleton
    await init_db()
    return await get_store()


class TestProjectManager:
    @pytest.mark.asyncio
    async def test_create_project(self, memory_store):
        from core.projects.manager import ProjectManager
        pm = ProjectManager()
        p = await pm.create_project("Test Project", goal="Build something")
        assert p["name"] == "Test Project"
        assert p["goal"] == "Build something"
        assert "id" in p

    @pytest.mark.asyncio
    async def test_list_projects(self, memory_store):
        from core.projects.manager import ProjectManager
        pm = ProjectManager()
        await pm.create_project("P1")
        await pm.create_project("P2")
        projects = await pm.list_projects()
        assert len(projects) >= 2

    @pytest.mark.asyncio
    async def test_add_and_complete_task(self, memory_store):
        from core.projects.manager import ProjectManager
        pm = ProjectManager()
        p = await pm.create_project("Test")
        task = await pm.add_task(p["id"], "Do something", priority=1)
        assert task["description"] == "Do something"
        assert not task["done"]

        done = await pm.complete_task(task["id"])
        assert done["done"]

    @pytest.mark.asyncio
    async def test_project_progress(self, memory_store):
        from core.projects.manager import ProjectManager
        pm = ProjectManager()
        p = await pm.create_project("Progress Test")
        t1 = await pm.add_task(p["id"], "Task 1")
        await pm.add_task(p["id"], "Task 2")
        await pm.complete_task(t1["id"])

        detail = await pm.get_project(p["id"])
        assert detail["progress"] == 50.0

    @pytest.mark.asyncio
    async def test_summary(self, memory_store):
        from core.projects.manager import ProjectManager
        pm = ProjectManager()
        summary = await pm.get_summary()
        assert "total_projects" in summary
        assert "by_status" in summary


# ── PHASE 8: Obsidian Sync ────────────────────────────────────────────────────

class TestObsidianSync:
    def test_parse_md_file(self, tmp_path):
        from core.integrations.sync.obsidian import parse_md_file
        md_file = tmp_path / "note.md"
        md_file.write_text("# Hello\n\nThis is a [[link]] and #tag test.", encoding="utf-8")
        result = parse_md_file(md_file)
        assert result["name"] == "note"
        assert "link" in result["tags"]
        assert "tag" in result["tags"]

    def test_parse_md_with_frontmatter(self, tmp_path):
        from core.integrations.sync.obsidian import parse_md_file
        md_file = tmp_path / "note2.md"
        md_file.write_text("---\ntitle: My Note\ntags: [a, b]\n---\n\nContent here.", encoding="utf-8")
        result = parse_md_file(md_file)
        assert result["title"] == "My Note"
        assert "Content here" in result["content"]

    @pytest.mark.asyncio
    async def test_import_vault_not_found(self):
        from core.integrations.sync.obsidian import import_vault
        result = await import_vault("/nonexistent/vault")
        assert "error" in result or result["files_imported"] == 0


# ── PHASE 9: Ouroboros ────────────────────────────────────────────────────────

class TestOuroboros:
    @pytest.mark.asyncio
    async def test_profile_step(self, memory_store):
        from core.self_improvement.ouroboros import step1_profile
        result = await step1_profile()
        assert result["step"] == "profile"
        assert "patterns" in result

    @pytest.mark.asyncio
    async def test_generate_step_no_patterns(self):
        from core.self_improvement.ouroboros import step2_generate
        result = await step2_generate([])
        assert result["step"] == "generate"
        assert result["proposals"] == []
        assert result["reason"] == "no_patterns"


# ── PHASE 10: Self-Healer ─────────────────────────────────────────────────────

class TestSelfHealer:
    @pytest.mark.asyncio
    async def test_check_database_ok(self, memory_store):
        from core.healing.self_healer import check_database, HealthStatus
        result = await check_database()
        assert result["status"] == HealthStatus.OK

    @pytest.mark.asyncio
    async def test_full_health_check_returns_dict(self, memory_store):
        from core.healing.self_healer import full_health_check
        result = await full_health_check()
        assert "overall" in result
        assert "components" in result
        assert isinstance(result["components"], list)

    def test_get_last_health_report_initial(self):
        from core.healing.self_healer import get_last_health_report
        report = get_last_health_report()
        assert isinstance(report, dict)


# ── PHASE 10: Federated Memory ────────────────────────────────────────────────

class TestFederatedMemory:
    @pytest.mark.asyncio
    async def test_push_and_pull(self, tmp_path):
        from core.memory.federated import FederatedMemory
        fm = FederatedMemory(node_id="test")
        fm._sync_dir = tmp_path / "test"
        fm._sync_dir.mkdir()

        await fm.push("key1", {"data": "value"})
        val = await fm.pull("key1")
        assert val == {"data": "value"}

    @pytest.mark.asyncio
    async def test_pull_missing_key(self, tmp_path):
        from core.memory.federated import FederatedMemory
        fm = FederatedMemory(node_id="test2")
        fm._sync_dir = tmp_path / "test2"
        fm._sync_dir.mkdir()

        val = await fm.pull("nonexistent")
        assert val is None

    def test_list_keys(self, tmp_path):
        from core.memory.federated import FederatedMemory
        import json
        fm = FederatedMemory(node_id="test3")
        fm._sync_dir = tmp_path / "test3"
        fm._sync_dir.mkdir()
        (fm._sync_dir / "k1.json").write_text(json.dumps({"key": "k1", "value": "x"}))

        keys = fm.list_keys()
        assert "k1" in keys

    def test_stats(self, tmp_path):
        from core.memory.federated import FederatedMemory
        fm = FederatedMemory(node_id="stats_test")
        fm._sync_dir = tmp_path / "stats_test"
        fm._sync_dir.mkdir()
        stats = fm.stats()
        assert stats["node_id"] == "stats_test"
        assert "stub_local_only" in stats["status"]


# ── PHASE 10: Agent Factory ───────────────────────────────────────────────────

class TestAgentFactory:
    def test_list_agents(self):
        from core.agents.factory import get_factory
        factory = get_factory()
        agents = factory.list_agents()
        assert len(agents) >= 4
        agent_types = {a["type"] for a in agents}
        assert "researcher" in agent_types
        assert "swarm" in agent_types

    def test_create_known_agent(self):
        from core.agents.factory import get_factory
        factory = get_factory()
        agent = factory.create("researcher")
        assert agent.agent_type == "researcher"

    def test_create_unknown_agent_raises(self):
        from core.agents.factory import get_factory
        factory = get_factory()
        with pytest.raises(ValueError):
            factory.create("nonexistent_agent_xyz")

    def test_register_custom_agent(self):
        from core.agents.factory import get_factory
        factory = get_factory()
        factory.register("test_agent", "A test agent", "core.agents.swarm", "run_swarm")
        agents = factory.list_agents()
        assert any(a["type"] == "test_agent" for a in agents)


# ── METACOGNITION API ─────────────────────────────────────────────────────────

class TestMetacognitionStore:
    @pytest.mark.asyncio
    async def test_save_and_list_quality(self, memory_store):
        store = memory_store
        await store.save_quality(
            session_id="test_sess",
            message="What is 2+2?",
            response="It is 4.",
            completeness=9.0,
            accuracy=10.0,
            helpfulness=8.5,
            overall=9.0,
            weak_points=None,
            improvement_hint=None,
        )
        records = await store.list_quality(session_id="test_sess")
        assert len(records) >= 1
        assert records[0].overall == 9.0

    @pytest.mark.asyncio
    async def test_quality_stats_empty(self, memory_store):
        store = memory_store
        stats = await store.get_quality_stats()
        # Should return zeros/defaults, not crash
        assert isinstance(stats, dict)

    @pytest.mark.asyncio
    async def test_weak_responses(self, memory_store):
        store = memory_store
        await store.save_quality(
            session_id="weak_test",
            message="test",
            response="short",
            completeness=3.0,
            accuracy=4.0,
            helpfulness=3.5,
            overall=3.5,
            weak_points='["краткость"]',
            improvement_hint="Be more detailed",
        )
        weak = await store.get_weak_responses(min_overall=5.0)
        assert len(weak) >= 1


# ── Cross-platform sync ───────────────────────────────────────────────────────

class TestCrossPlatformSync:
    def test_copy_to_clipboard(self):
        from core.integrations.sync.cross_platform import copy_to_clipboard
        # Should not raise; may return True or False depending on env
        result = copy_to_clipboard("test text")
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_export_knowledge_no_nodes(self, tmp_path, memory_store):
        from core.integrations.sync.cross_platform import export_knowledge
        result = await export_knowledge(output_path=tmp_path)
        assert result["success"]
        assert result["nodes_exported"] == 0
        assert Path(result["path"]).exists()

    @pytest.mark.asyncio
    async def test_import_nonexistent_file(self):
        from core.integrations.sync.cross_platform import import_knowledge
        result = await import_knowledge("/nonexistent/file.json")
        assert not result["success"]
        assert "not found" in result["error"]
