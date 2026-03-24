"""
ROSA OS — Regression Tester.

Runs the test suite on demand and stores results for trend analysis.
Never blocks startup — always called asynchronously.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.audit.regression")

_RESULTS_FILE = Path("memory/regression_results.json")


@dataclass
class TestRun:
    timestamp: str
    passed: int
    failed: int
    errors: int
    total: int
    duration_s: float
    exit_code: int
    summary: str
    failed_tests: list[str]


class RegressionTester:
    """Runs pytest and tracks pass/fail trends over time."""

    def __init__(self, tests_dir: str = "tests/"):
        self.tests_dir = tests_dir
        self._history: list[TestRun] = self._load_history()

    def _load_history(self) -> list[TestRun]:
        if not _RESULTS_FILE.exists():
            return []
        try:
            data = json.loads(_RESULTS_FILE.read_text())
            return [TestRun(**r) for r in data.get("runs", [])]
        except Exception:
            return []

    def _save_history(self) -> None:
        try:
            _RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            # Keep last 50 runs
            runs = self._history[-50:]
            _RESULTS_FILE.write_text(
                json.dumps(
                    {"runs": [asdict(r) for r in runs]},
                    indent=2,
                    ensure_ascii=False,
                )
            )
        except Exception:
            pass

    def _parse_pytest_output(self, stdout: str, exit_code: int) -> dict:
        """Parse pytest -v output to extract pass/fail counts."""
        passed = 0
        failed = 0
        errors = 0
        failed_tests: list[str] = []

        for line in stdout.splitlines():
            # e.g. "5 passed, 2 failed, 1 error in 3.45s"
            import re
            m = re.search(r"(\d+) passed", line)
            if m:
                passed = int(m.group(1))
            m = re.search(r"(\d+) failed", line)
            if m:
                failed = int(m.group(1))
            m = re.search(r"(\d+) error", line)
            if m:
                errors = int(m.group(1))
            # Collect FAILED test names
            m = re.match(r"FAILED (.+?) - ", line)
            if m:
                failed_tests.append(m.group(1).strip())

        total = passed + failed + errors
        if exit_code == 0:
            summary = f"✅ All {total} tests passed"
        else:
            summary = f"❌ {failed} failed, {errors} errors / {total} total"

        return {
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "summary": summary,
            "failed_tests": failed_tests,
        }

    async def run_tests(self, extra_args: list[str] | None = None) -> TestRun:
        """Run pytest asynchronously and return a TestRun record."""
        cmd = ["python3", "-m", "pytest", self.tests_dir, "-v", "--tb=no", "-q"]
        if extra_args:
            cmd.extend(extra_args)

        t0 = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
            exit_code = proc.returncode or 0
            stdout = stdout_bytes.decode(errors="replace")
        except asyncio.TimeoutError:
            logger.warning("Regression test timed out after 120s")
            stdout = ""
            exit_code = 2
        except Exception as exc:
            logger.error("Regression test error: %s", exc)
            stdout = str(exc)
            exit_code = 2

        duration = time.monotonic() - t0
        parsed = self._parse_pytest_output(stdout, exit_code)

        run = TestRun(
            timestamp=datetime.now(timezone.utc).isoformat(),
            passed=parsed["passed"],
            failed=parsed["failed"],
            errors=parsed["errors"],
            total=parsed["total"],
            duration_s=round(duration, 2),
            exit_code=exit_code,
            summary=parsed["summary"],
            failed_tests=parsed["failed_tests"],
        )

        self._history.append(run)
        self._save_history()
        logger.info("Regression: %s (%.1fs)", run.summary, run.duration_s)
        return run

    def get_trend(self, last_n: int = 10) -> dict:
        """Return pass-rate trend for last N runs."""
        runs = self._history[-last_n:]
        if not runs:
            return {"runs": 0, "avg_pass_rate": 0.0, "trend": "no data"}

        rates = [r.passed / max(r.total, 1) * 100 for r in runs]
        avg = sum(rates) / len(rates)
        if len(rates) >= 2:
            trend = "improving" if rates[-1] > rates[0] else "declining" if rates[-1] < rates[0] else "stable"
        else:
            trend = "stable"

        return {
            "runs": len(runs),
            "avg_pass_rate": round(avg, 1),
            "latest_pass_rate": round(rates[-1], 1),
            "trend": trend,
            "last_summary": runs[-1].summary if runs else "",
        }

    def get_history(self, limit: int = 20) -> list[TestRun]:
        return self._history[-limit:]


_tester: Optional[RegressionTester] = None


def get_regression_tester() -> RegressionTester:
    global _tester
    if _tester is None:
        _tester = RegressionTester()
    return _tester
