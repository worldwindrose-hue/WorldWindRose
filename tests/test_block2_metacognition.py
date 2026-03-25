"""Tests for Block 2: Meta-cognition, CapabilityMap, CodeGenesis."""

from __future__ import annotations

import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, AsyncMock


# ── CAPABILITY MAP ─────────────────────────────────────────────────────────

def test_capability_map_load_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.metacognition.capability_map import CapabilityMap
    cap_map = CapabilityMap()
    caps = cap_map.to_dict()
    assert len(caps) > 5
    assert "coding" in caps or "python" in caps


def test_capability_record_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.metacognition.capability_map import CapabilityMap
    cap_map = CapabilityMap()
    cap_map._ensure("test_skill").level = 2.0
    cap_map.record_success("test_skill")
    assert cap_map.get("test_skill").level > 2.0
    assert cap_map.get("test_skill").total_uses == 1


def test_capability_record_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.metacognition.capability_map import CapabilityMap
    cap_map = CapabilityMap()
    cap_map._ensure("weak_skill").level = 3.0
    cap_map.record_failure("weak_skill")
    assert cap_map.get("weak_skill").level < 3.0


def test_capability_get_gaps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.metacognition.capability_map import CapabilityMap
    cap_map = CapabilityMap()
    # Force a low level
    cap_map._ensure("bad_skill").level = 1.5
    cap_map.save()
    gaps = cap_map.get_gaps()
    names = [g.name for g in gaps]
    assert "bad_skill" in names


def test_capability_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.metacognition.capability_map import CapabilityMap
    cap_map = CapabilityMap()
    summary = cap_map.summary()
    assert isinstance(summary, dict)
    assert all(isinstance(v, float) for v in summary.values())


# ── SELF REFLECTION ────────────────────────────────────────────────────────

def test_reflection_result_dataclass():
    from core.metacognition.self_reflection import ReflectionResult
    r = ReflectionResult(
        response_id="abc123",
        score=0.85,
        hallucination_risk=0.2,
        completeness=0.9,
        gaps=["gap1"],
        improvement_tasks=["task1"],
    )
    assert r.score == 0.85
    assert r.response_id == "abc123"
    assert r.timestamp != ""
    d = r.to_dict()
    assert d["score"] == 0.85


@pytest.mark.asyncio
async def test_reflect_heuristic_no_llm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Patch LLM to simulate unavailability
    with patch("core.metacognition.self_reflection._llm_reflect", new_callable=AsyncMock, return_value=None):
        from core.metacognition.self_reflection import reflect_on_response
        result = await reflect_on_response("Что такое Python?", "Python — язык программирования.")
    assert 0.0 <= result.score <= 1.0
    assert 0.0 <= result.hallucination_risk <= 1.0


# ── GAP ANALYZER ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gap_analyzer_empty_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from core.metacognition.gap_analyzer import weekly_gap_report
    report = await weekly_gap_report(days=7)
    assert "responses_analyzed" in report
    assert report["responses_analyzed"] == 0 or isinstance(report["responses_analyzed"], int)


@pytest.mark.asyncio
async def test_gap_analyzer_with_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Create fake reflection log
    log_file = tmp_path / "memory" / "self_reflection.log"
    log_file.parent.mkdir(parents=True)
    entries = [
        {"response_id": f"r{i}", "score": 0.4, "hallucination_risk": 0.5,
         "completeness": 0.5, "gaps": ["pdf parsing"], "improvement_tasks": ["learn pdf"],
         "timestamp": "2026-03-25T10:00:00+00:00"}
        for i in range(5)
    ]
    log_file.write_text("\n".join(json.dumps(e) for e in entries))

    with patch("core.metacognition.gap_analyzer._REPORT_FILE", tmp_path / "memory" / "gap_reports.jsonl"):
        with patch("core.metacognition.gap_analyzer.load_reflections", return_value=entries):
            from core.metacognition.gap_analyzer import weekly_gap_report
            report = await weekly_gap_report(days=7)
    assert report["responses_analyzed"] == 5
    assert "gaps" in report


# ── CODE GENESIS ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_test_passes():
    from core.self_improvement.code_genesis import sandbox_test
    code = "def add(a, b):\n    return a + b\n"
    tests = "from module import add\ndef test_add():\n    assert add(1, 2) == 3\n"
    passed, output = await sandbox_test(code, tests)
    assert passed is True
    assert "passed" in output.lower() or "1" in output


@pytest.mark.asyncio
async def test_sandbox_test_fails():
    from core.self_improvement.code_genesis import sandbox_test
    code = "def add(a, b):\n    return a - b  # wrong\n"
    tests = "from module import add\ndef test_add():\n    assert add(1, 2) == 3\n"
    passed, output = await sandbox_test(code, tests)
    assert passed is False


# ── CAPABILITIES API ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capabilities_api_endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from fastapi.testclient import TestClient

    # Import after chdir so capability_map uses tmp_path
    with patch("core.metacognition.capability_map._CAP_FILE", tmp_path / "memory" / "capabilities.json"):
        from core.api.capabilities import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        r = client.get("/api/capabilities")
        assert r.status_code == 200
        data = r.json()
        assert "capabilities" in data
        assert "summary" in data
