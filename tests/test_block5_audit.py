"""Tests for Block 5 — StartupAudit + SelfDebugger + RegressionTester."""
from __future__ import annotations

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock


# ── StartupAudit ──────────────────────────────────────────────────────────


class TestStartupAudit:
    @pytest.mark.asyncio
    async def test_run_startup_audit_returns_report(self):
        """run_startup_audit() returns AuditReport with required fields."""
        from core.audit.startup_audit import run_startup_audit, AuditReport
        report = await run_startup_audit()
        assert isinstance(report, AuditReport)
        assert hasattr(report, "checks")
        assert hasattr(report, "score")
        assert hasattr(report, "passed")
        assert hasattr(report, "failed")
        assert hasattr(report, "warned")
        assert isinstance(report.checks, list)
        assert len(report.checks) > 0

    @pytest.mark.asyncio
    async def test_audit_score_range(self):
        """Audit score is between 0 and 100."""
        from core.audit.startup_audit import run_startup_audit
        report = await run_startup_audit()
        assert 0.0 <= report.score <= 100.0

    @pytest.mark.asyncio
    async def test_audit_check_statuses(self):
        """All check statuses are valid."""
        from core.audit.startup_audit import run_startup_audit
        report = await run_startup_audit()
        valid_statuses = {"pass", "warn", "fail"}
        for check in report.checks:
            assert check.status in valid_statuses

    @pytest.mark.asyncio
    async def test_audit_to_dict(self):
        """AuditReport.to_dict() returns serializable dict."""
        from core.audit.startup_audit import run_startup_audit
        report = await run_startup_audit()
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "checks" in d
        assert "score" in d
        # Should be JSON-serializable
        json.dumps(d)

    @pytest.mark.asyncio
    async def test_audit_from_dict_roundtrip(self):
        """AuditReport serializes and deserializes correctly."""
        from core.audit.startup_audit import run_startup_audit, AuditReport
        report = await run_startup_audit()
        d = report.to_dict()
        restored = AuditReport.from_dict(d)
        assert restored.score == report.score
        assert len(restored.checks) == len(report.checks)

    def test_get_last_audit_no_file(self, tmp_path):
        """get_last_audit() returns None if no file exists."""
        from core.audit import startup_audit
        original = startup_audit._AUDIT_LOG
        startup_audit._AUDIT_LOG = tmp_path / "nonexistent.json"
        result = startup_audit.get_last_audit()
        startup_audit._AUDIT_LOG = original
        assert result is None

    @pytest.mark.asyncio
    async def test_audit_saves_to_file(self, tmp_path):
        """run_startup_audit() saves JSON to disk."""
        from core.audit import startup_audit
        original = startup_audit._AUDIT_LOG
        startup_audit._AUDIT_LOG = tmp_path / "audit_log.json"
        try:
            report = await startup_audit.run_startup_audit()
            assert startup_audit._AUDIT_LOG.exists()
            data = json.loads(startup_audit._AUDIT_LOG.read_text())
            assert "score" in data
        finally:
            startup_audit._AUDIT_LOG = original


# ── SelfDebugger ──────────────────────────────────────────────────────────


class TestSelfDebugger:
    def test_debugger_singleton(self):
        """get_self_debugger() returns same instance."""
        from core.audit.self_debugger import get_self_debugger, SelfDebugger
        a = get_self_debugger()
        b = get_self_debugger()
        assert a is b
        assert isinstance(a, SelfDebugger)

    def test_scan_empty_text(self):
        """Scanning empty text returns empty dict."""
        from core.audit.self_debugger import SelfDebugger
        d = SelfDebugger()
        result = d.scan_log_text("")
        assert result == {}

    def test_scan_missing_module_error(self):
        """ModuleNotFoundError is detected."""
        from core.audit.self_debugger import SelfDebugger
        d = SelfDebugger()
        log = "ModuleNotFoundError: No module named 'chromadb'"
        result = d.scan_log_text(log)
        assert "missing_dependency" in result
        assert "chromadb" in result["missing_dependency"].fix_suggestion

    def test_scan_sqlite_error(self):
        """SQLite table error is detected."""
        from core.audit.self_debugger import SelfDebugger
        d = SelfDebugger()
        log = "sqlite3.OperationalError: no such table: users"
        result = d.scan_log_text(log)
        assert "db_schema" in result

    def test_scan_timeout_error(self):
        """TimeoutError is detected."""
        from core.audit.self_debugger import SelfDebugger
        d = SelfDebugger()
        log = "asyncio.TimeoutError: operation timed out"
        result = d.scan_log_text(log)
        assert "timeout" in result

    def test_generate_report(self):
        """generate_report returns DebugReport."""
        from core.audit.self_debugger import SelfDebugger, ErrorOccurrence, DebugReport
        from datetime import datetime, timezone
        d = SelfDebugger()
        now = datetime.now(timezone.utc).isoformat()
        occ = {
            "timeout": ErrorOccurrence(
                pattern="TimeoutError",
                category="timeout",
                count=3,
                first_seen=now,
                last_seen=now,
                fix_suggestion="Increase timeout",
                severity="warn",
            )
        }
        report = d.generate_report(occ)
        assert isinstance(report, DebugReport)
        assert report.total_errors == 3
        assert report.top_category == "timeout"
        assert len(report.action_items) >= 1

    def test_save_patch_suggestion(self, tmp_path):
        """save_patch_suggestion writes a file."""
        from core.audit import self_debugger
        original = self_debugger._PATCHES_DIR
        self_debugger._PATCHES_DIR = tmp_path / "patches"
        d = self_debugger.SelfDebugger()
        path = d.save_patch_suggestion("timeout", "Use asyncio.wait_for with 60s")
        assert path.exists()
        assert "timeout" in path.name
        self_debugger._PATCHES_DIR = original


# ── RegressionTester ──────────────────────────────────────────────────────


class TestRegressionTester:
    def test_tester_singleton(self):
        """get_regression_tester() returns same instance."""
        from core.audit.regression_tester import get_regression_tester, RegressionTester
        a = get_regression_tester()
        b = get_regression_tester()
        assert a is b
        assert isinstance(a, RegressionTester)

    def test_parse_pytest_output_all_pass(self):
        """_parse_pytest_output correctly parses passing output."""
        from core.audit.regression_tester import RegressionTester
        t = RegressionTester()
        output = "5 passed in 1.23s"
        result = t._parse_pytest_output(output, 0)
        assert result["passed"] == 5
        assert result["failed"] == 0
        assert "✅" in result["summary"]

    def test_parse_pytest_output_with_failures(self):
        """_parse_pytest_output correctly parses failure output."""
        from core.audit.regression_tester import RegressionTester
        t = RegressionTester()
        output = "3 passed, 2 failed in 2.00s\nFAILED tests/test_foo.py::test_bar - AssertionError"
        result = t._parse_pytest_output(output, 1)
        assert result["passed"] == 3
        assert result["failed"] == 2
        assert "test_foo" in str(result["failed_tests"])

    def test_get_trend_empty(self):
        """get_trend() with no runs returns no-data dict."""
        from core.audit.regression_tester import RegressionTester
        t = RegressionTester()
        t._history = []
        trend = t.get_trend()
        assert trend["runs"] == 0

    def test_get_trend_with_data(self):
        """get_trend() calculates average pass rate."""
        from core.audit.regression_tester import RegressionTester, TestRun
        from datetime import datetime, timezone
        t = RegressionTester()
        now = datetime.now(timezone.utc).isoformat()
        t._history = [
            TestRun(timestamp=now, passed=10, failed=0, errors=0, total=10,
                    duration_s=1.0, exit_code=0, summary="✅", failed_tests=[]),
            TestRun(timestamp=now, passed=8, failed=2, errors=0, total=10,
                    duration_s=1.5, exit_code=1, summary="❌", failed_tests=["a", "b"]),
        ]
        trend = t.get_trend()
        assert trend["runs"] == 2
        assert trend["avg_pass_rate"] == 90.0  # (100 + 80) / 2

    @pytest.mark.asyncio
    async def test_run_tests_mock(self):
        """run_tests() calls subprocess and returns TestRun."""
        from core.audit.regression_tester import RegressionTester
        t = RegressionTester()
        t._history = []

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"5 passed in 1.0s", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            run = await t.run_tests()

        assert run.exit_code == 0
        assert run.passed == 5

    def test_get_history(self):
        """get_history() respects limit."""
        from core.audit.regression_tester import RegressionTester, TestRun
        from datetime import datetime, timezone
        t = RegressionTester()
        now = datetime.now(timezone.utc).isoformat()
        t._history = [
            TestRun(timestamp=now, passed=i, failed=0, errors=0, total=i,
                    duration_s=1.0, exit_code=0, summary="✅", failed_tests=[])
            for i in range(30)
        ]
        history = t.get_history(limit=10)
        assert len(history) == 10
