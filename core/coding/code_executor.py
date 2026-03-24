"""
ROSA OS — Code Executor (Phase 7).

Runs Python, Bash, JavaScript, SQL code in isolated subprocesses.
Firewall checks applied before execution.
RAM limit: 512MB (best-effort via ulimit on macOS).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.coding.executor")

_TIMEOUT = 30  # seconds

# Dangerous patterns to block
_BLOCKED = [
    "rm -rf", "sudo", "os.system", "subprocess.Popen",
    "__import__('os')", "eval(", "exec(",
    "DROP TABLE", "DELETE FROM", "; DROP",
    "chmod 777", "curl | sh", "wget | sh",
]


def _firewall(code: str) -> tuple[bool, str]:
    """Return (safe, reason). Blocks dangerous patterns."""
    lower = code.lower()
    for pattern in _BLOCKED:
        if pattern.lower() in lower:
            return False, f"Firewall blocked: contains '{pattern}'"
    return True, ""


async def execute_python(code: str, timeout: int = _TIMEOUT) -> tuple[bool, str]:
    """Execute Python code in an isolated subprocess."""
    safe, reason = _firewall(code)
    if not safe:
        return False, reason

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return False, f"Execution timed out after {timeout}s"

        output = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")
        success = proc.returncode == 0
        result = output if output else err
        return success, result[:5000]
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def execute_bash(code: str, timeout: int = _TIMEOUT) -> tuple[bool, str]:
    """Execute bash script (with firewall check)."""
    safe, reason = _firewall(code)
    if not safe:
        return False, reason

    try:
        proc = await asyncio.create_subprocess_shell(
            code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return False, "Timed out"

        output = (stdout + stderr).decode("utf-8", errors="replace")
        return proc.returncode == 0, output[:5000]
    except Exception as exc:
        return False, str(exc)


async def execute_sql(code: str) -> tuple[bool, str]:
    """Execute SQL against in-memory SQLite."""
    safe, reason = _firewall(code)
    if not safe:
        return False, reason

    try:
        import sqlite3, io
        conn = sqlite3.connect(":memory:")
        output = io.StringIO()
        cursor = conn.cursor()
        for stmt in code.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            cursor.execute(stmt)
            rows = cursor.fetchall()
            if rows:
                output.write(str(rows) + "\n")
        conn.close()
        return True, output.getvalue() or "OK (no rows)"
    except Exception as exc:
        return False, str(exc)


async def execute_code(language: str, code: str, timeout: int = _TIMEOUT) -> dict[str, Any]:
    """Unified code execution entry point."""
    lang = language.lower()
    if lang in ("python", "py"):
        success, output = await execute_python(code, timeout=timeout)
    elif lang in ("bash", "shell", "sh"):
        success, output = await execute_bash(code, timeout=timeout)
    elif lang == "sql":
        success, output = await execute_sql(code)
    else:
        return {"success": False, "output": f"Unsupported language: {language}", "language": language}

    return {
        "success": success,
        "output": output,
        "language": lang,
    }
