"""
Tests for ROSA OS v6+ Autonomous Features:
- Smart Parser (swarm agents)
- ProactiveProblemSolver
- AppleScript Mac control
- Ollama LocalRouter model selection
"""

from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─── Smart Parser Tests ────────────────────────────────────────────────────

class TestDetectPlatform:
    def test_instagram(self):
        from core.agents.smart_parser import detect_platform, Platform
        assert detect_platform("https://www.instagram.com/p/ABC123/") == Platform.INSTAGRAM

    def test_tiktok(self):
        from core.agents.smart_parser import detect_platform, Platform
        assert detect_platform("https://www.tiktok.com/@user/video/123") == Platform.TIKTOK

    def test_youtube(self):
        from core.agents.smart_parser import detect_platform, Platform
        assert detect_platform("https://youtu.be/abc123") == Platform.YOUTUBE

    def test_twitter(self):
        from core.agents.smart_parser import detect_platform, Platform
        assert detect_platform("https://twitter.com/user/status/123") == Platform.TWITTER

    def test_generic(self):
        from core.agents.smart_parser import detect_platform, Platform
        assert detect_platform("https://example.com/article") == Platform.GENERIC


class TestParseResult:
    def test_parse_result_defaults(self):
        from core.agents.smart_parser import ParseResult, Platform
        r = ParseResult(url="https://test.com", platform=Platform.GENERIC, success=False)
        assert r.attempts == []
        assert r.alternatives == []
        assert r.solution_saved is False

    def test_parse_attempt(self):
        from core.agents.smart_parser import ParseAttempt
        a = ParseAttempt(method="yt-dlp", success=True, duration_ms=123.4)
        assert a.success is True
        assert a.duration_ms == 123.4


class TestSmartParseBasic:
    @pytest.mark.asyncio
    async def test_smart_parse_no_ytdlp(self):
        """Smart parse falls back gracefully when yt-dlp not available."""
        from core.agents.smart_parser import smart_parse
        statuses = []

        # Mock all download methods to fail
        with patch("core.agents.smart_parser._try_ytdlp", new=AsyncMock(return_value=(False, "yt-dlp not installed", ""))), \
             patch("core.agents.smart_parser._try_requests_extract", new=AsyncMock(return_value=(False, "no content", ""))), \
             patch("core.agents.smart_parser._run_swarm", new=AsyncMock(return_value=[])), \
             patch("core.agents.smart_parser._synthesize_solution", new=AsyncMock(return_value=[])):
            result = await smart_parse(
                "https://www.instagram.com/p/TEST/",
                status_cb=lambda m: statuses.append(m)
            )

        assert result.url == "https://www.instagram.com/p/TEST/"
        assert result.success is False
        assert len(result.attempts) >= 1
        assert len(statuses) >= 1

    @pytest.mark.asyncio
    async def test_smart_parse_ytdlp_success(self):
        """Smart parse returns success when yt-dlp works."""
        from core.agents.smart_parser import smart_parse

        with patch("core.agents.smart_parser._try_ytdlp", new=AsyncMock(return_value=(True, "/tmp/video.mp4", "Test Video"))):
            result = await smart_parse("https://www.youtube.com/watch?v=TEST")

        assert result.success is True
        assert result.media_path == "/tmp/video.mp4"
        assert result.metadata.get("title") == "Test Video"

    @pytest.mark.asyncio
    async def test_smart_parse_requests_fallback(self):
        """Smart parse falls back to requests extraction."""
        from core.agents.smart_parser import smart_parse

        with patch("core.agents.smart_parser._try_ytdlp", new=AsyncMock(return_value=(False, "error", ""))), \
             patch("core.agents.smart_parser._try_requests_extract", new=AsyncMock(return_value=(True, "Great article content here!", ""))):
            result = await smart_parse("https://example.com/article")

        assert result.success is True
        assert result.content == "Great article content here!"


class TestSwarmAgents:
    @pytest.mark.asyncio
    async def test_github_agent(self):
        from core.agents.smart_parser import _github_agent, Platform
        result = await _github_agent(Platform.INSTAGRAM)
        assert result["agent"] == "GitHubAgent"
        assert "instaloader" in result["libraries"]

    @pytest.mark.asyncio
    async def test_docs_agent_instagram(self):
        from core.agents.smart_parser import _docs_agent, Platform
        result = await _docs_agent(Platform.INSTAGRAM, "blocked by bot protection")
        assert result["agent"] == "DocsAgent"
        assert len(result["fixes"]) >= 2
        # Blocking error should trigger UA rotation hint
        hints_text = " ".join(result["fixes"]).lower()
        assert "ua" in hints_text or "user" in hints_text or "block" in hints_text

    @pytest.mark.asyncio
    async def test_docs_agent_youtube(self):
        from core.agents.smart_parser import _docs_agent, Platform
        result = await _docs_agent(Platform.YOUTUBE, "age restricted")
        assert "yt-dlp" in " ".join(result["fixes"])


# ─── ProactiveProblemSolver Tests ─────────────────────────────────────────

class TestProactiveProblemSolver:
    def test_classify_media_download(self):
        from core.prediction.proactive import ProactiveProblemSolver
        solver = ProactiveProblemSolver()
        assert solver._classify("download instagram video failed") == "media_download"

    def test_classify_missing_dependency(self):
        from core.prediction.proactive import ProactiveProblemSolver
        solver = ProactiveProblemSolver()
        assert solver._classify("ModuleNotFoundError: No module named 'chromadb'") == "missing_dependency"

    def test_classify_network_error(self):
        from core.prediction.proactive import ProactiveProblemSolver
        solver = ProactiveProblemSolver()
        assert solver._classify("connection timeout after 30s") == "network_error"

    def test_classify_auth_error(self):
        from core.prediction.proactive import ProactiveProblemSolver
        solver = ProactiveProblemSolver()
        assert solver._classify("401 Unauthorized — check API key") == "auth_error"

    def test_classify_general(self):
        from core.prediction.proactive import ProactiveProblemSolver
        solver = ProactiveProblemSolver()
        assert solver._classify("something weird happened") == "general_error"

    @pytest.mark.asyncio
    async def test_lookup_knowledge_graph_empty(self):
        from core.prediction.proactive import ProactiveProblemSolver
        solver = ProactiveProblemSolver()
        # No memory set up — should return None gracefully
        result = await solver._lookup_knowledge_graph("test problem", "general_error")
        assert result is None

    @pytest.mark.asyncio
    async def test_explain_and_propose_media(self):
        from core.prediction.proactive import ProactiveProblemSolver
        solver = ProactiveProblemSolver()
        explanation, alternatives = await solver._explain_and_propose(
            "instagram download failed", "media_download", ["try1", "try2"]
        )
        assert "instagram" in explanation.lower() or "автономный" in explanation.lower()
        assert len(alternatives) >= 1

    @pytest.mark.asyncio
    async def test_autonomy_loop_timeout(self):
        """Solver respects timeout limit."""
        from core.prediction.proactive import ProactiveProblemSolver

        solver = ProactiveProblemSolver()
        # Set very short timeout
        solver.TIMEOUT_SECONDS = 0

        with patch.object(solver, "_lookup_knowledge_graph", new=AsyncMock(return_value=None)), \
             patch.object(solver, "_find_solution", new=AsyncMock(return_value="try something")), \
             patch.object(solver, "_apply_solution", new=AsyncMock(return_value=(False, "failed"))):
            result = await solver.autonomy_loop("test problem that times out")

        assert result.solved is False

    @pytest.mark.asyncio
    async def test_solve_problem_convenience(self):
        """solve_problem() convenience function works."""
        from core.prediction.proactive import solve_problem

        with patch("core.prediction.proactive.ProactiveProblemSolver._lookup_knowledge_graph",
                   new=AsyncMock(return_value="use yt-dlp with --cookies flag")):
            result = await solve_problem("download video from youtube failed")

        assert result.solved is True
        assert "yt-dlp" in result.solution

    @pytest.mark.asyncio
    async def test_get_problem_solver_singleton(self):
        from core.prediction.proactive import get_problem_solver
        s1 = get_problem_solver()
        s2 = get_problem_solver()
        assert s1 is s2


# ─── Mac Control (AppleScript) Tests ──────────────────────────────────────

class TestAppleScript:
    def test_run_applescript_success(self):
        from core.mac_control.applescript import run_applescript
        ok, out = run_applescript("return 42")
        assert ok is True
        assert "42" in out

    def test_run_applescript_invalid(self):
        from core.mac_control.applescript import run_applescript
        ok, out = run_applescript("this is not valid AppleScript !!!")
        assert ok is False
        assert out  # should have error message

    def test_run_applescript_timeout(self):
        from core.mac_control.applescript import run_applescript
        # Very short timeout to trigger timeout handling (delay beyond limit)
        ok, out = run_applescript("delay 10", timeout=1)
        assert ok is False
        assert "timeout" in out.lower()

    def test_open_app_returns_dict(self):
        from core.mac_control.applescript import open_app
        # Just verify structure — actual app opening tested separately
        result = open_app("Finder")
        assert "ok" in result
        assert "app" in result
        assert result["app"] == "Finder"

    def test_notify_returns_dict(self):
        from core.mac_control.applescript import notify
        result = notify("ROSA Test", "Test notification from pytest")
        assert "ok" in result

    def test_take_screenshot_returns_structure(self):
        from core.mac_control.applescript import take_screenshot
        result = take_screenshot()
        assert "ok" in result
        if result["ok"]:
            assert "base64_png" in result
            assert result["width"] > 0
            assert result["height"] > 0

    def test_check_permissions(self):
        from core.mac_control.applescript import check_automation_permissions
        result = check_automation_permissions()
        assert "system_events" in result
        assert "screencapture" in result
        assert "all_ok" in result

    def test_run_shell_blocks_dangerous(self):
        from core.mac_control.applescript import run_shell_command
        result = run_shell_command("rm -rf /tmp/test")
        assert result["ok"] is False
        assert "Blocked" in result["error"]

    def test_run_shell_safe_command(self):
        from core.mac_control.applescript import run_shell_command
        result = run_shell_command("echo hello")
        assert "ok" in result


# ─── Ollama LocalRouter model selection ────────────────────────────────────

class TestOllamaModelSelection:
    @pytest.mark.asyncio
    async def test_prefers_rosa_model(self):
        """LocalRouter should prefer rosa:latest over llama3.2."""
        from core.router.local_router import LocalRouter
        router = LocalRouter()

        captured_model = []

        async def mock_list():
            return {"models": [
                {"name": "llama3.2"},
                {"name": "rosa:latest"},
                {"name": "qwen2.5:3b"},
            ]}

        async def mock_generate(model, prompt):
            captured_model.append(model)
            return {"response": "test response"}

        with patch("ollama.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.list = AsyncMock(side_effect=mock_list)
            instance.generate = AsyncMock(side_effect=mock_generate)
            MockClient.return_value = instance

            await router._call_ollama([{"role": "user", "content": "test"}])

        assert captured_model[0] == "rosa:latest"

    @pytest.mark.asyncio
    async def test_fallback_to_llama32(self):
        """Falls back to llama3.2 if rosa:latest unavailable."""
        from core.router.local_router import LocalRouter
        router = LocalRouter()

        captured_model = []

        async def mock_list():
            return {"models": [{"name": "llama3.2"}]}

        async def mock_generate(model, prompt):
            captured_model.append(model)
            return {"response": "test response"}

        with patch("ollama.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.list = AsyncMock(side_effect=mock_list)
            instance.generate = AsyncMock(side_effect=mock_generate)
            MockClient.return_value = instance

            await router._call_ollama([{"role": "user", "content": "test"}])

        assert captured_model[0] == "llama3.2"

    @pytest.mark.asyncio
    async def test_handles_list_failure(self):
        """Handles ollama.list() failure gracefully."""
        from core.router.local_router import LocalRouter
        router = LocalRouter()

        captured_model = []

        async def mock_generate(model, prompt):
            captured_model.append(model)
            return {"response": "fallback response"}

        with patch("ollama.AsyncClient") as MockClient:
            instance = MagicMock()
            instance.list = AsyncMock(side_effect=Exception("connection refused"))
            instance.generate = AsyncMock(side_effect=mock_generate)
            MockClient.return_value = instance

            result = await router._call_ollama([{"role": "user", "content": "test"}])

        # Should still return a response (using default model)
        assert result == "fallback response"
