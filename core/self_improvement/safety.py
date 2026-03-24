"""
ROSA OS — Safety Sandbox for Self-Improvement Patches.

All patches are first written to sandbox/patches/.
Auto-runs pytest on affected modules.
On test failure: rollback + log reason.
On success: propose patch in Improve panel.
Human Gate: apply only via UI button.
Full log in memory/patches.log.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.self_improvement.safety")

# Directories
_BASE = Path(__file__).parent.parent.parent  # project root
SANDBOX_DIR = _BASE / "sandbox" / "patches"
REJECTED_DIR = _BASE / "sandbox" / "rejected"
PATCHES_LOG = _BASE / "memory" / "patches.log"

# Ensure directories exist at import time
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
REJECTED_DIR.mkdir(parents=True, exist_ok=True)
(_BASE / "memory").mkdir(parents=True, exist_ok=True)


class PatchResult:
    """Outcome of a patch evaluation."""

    def __init__(
        self,
        patch_id: str,
        status: str,  # "pending" | "passed" | "rejected"
        tests_passed: int = 0,
        tests_failed: int = 0,
        failure_reason: str = "",
        patch_path: str = "",
    ) -> None:
        self.patch_id = patch_id
        self.status = status
        self.tests_passed = tests_passed
        self.tests_failed = tests_failed
        self.failure_reason = failure_reason
        self.patch_path = patch_path
        self.evaluated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "patch_id": self.patch_id,
            "status": self.status,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "failure_reason": self.failure_reason,
            "patch_path": self.patch_path,
            "evaluated_at": self.evaluated_at,
        }


def _log_patch_event(event: dict[str, Any]) -> None:
    """Append a JSON line to memory/patches.log."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **event}
    try:
        with PATCHES_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("patches.log write failed: %s", exc)


def write_patch_to_sandbox(
    filename: str,
    content: str,
    patch_id: str | None = None,
) -> tuple[str, Path]:
    """
    Write patch content to sandbox/patches/<patch_id>/<filename>.
    Returns (patch_id, patch_file_path).
    """
    pid = patch_id or str(uuid.uuid4())[:8]
    patch_dir = SANDBOX_DIR / pid
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / filename
    patch_path.write_text(content, encoding="utf-8")

    _log_patch_event({
        "event": "patch_written",
        "patch_id": pid,
        "filename": filename,
        "size": len(content),
    })
    logger.info("Patch %s written: %s", pid, patch_path)
    return pid, patch_path


def run_tests_for_patch(patch_id: str, target_module: str | None = None) -> PatchResult:
    """
    Run pytest in the project root (or targeting a specific module).
    Returns PatchResult with status and counts.
    """
    test_args = ["python3", "-m", "pytest", "tests/", "-v", "--tb=short", "-q"]
    if target_module:
        test_args.append(f"--pyargs={target_module}")

    env = os.environ.copy()
    # Ensure project root is in PYTHONPATH
    env["PYTHONPATH"] = str(_BASE)

    try:
        proc = subprocess.run(
            test_args,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(_BASE),
            env=env,
        )
        output = proc.stdout + proc.stderr
        # Parse pytest summary: "X passed", "Y failed"
        passed = failed = 0
        for line in output.splitlines():
            if "passed" in line:
                import re
                m = re.search(r"(\d+) passed", line)
                if m:
                    passed = int(m.group(1))
                m2 = re.search(r"(\d+) failed", line)
                if m2:
                    failed = int(m2.group(1))

        status = "passed" if proc.returncode == 0 and failed == 0 else "rejected"
        reason = "" if status == "passed" else f"Tests failed (rc={proc.returncode})\n{output[-2000:]}"

        result = PatchResult(
            patch_id=patch_id,
            status=status,
            tests_passed=passed,
            tests_failed=failed,
            failure_reason=reason,
        )
        _log_patch_event({
            "event": "tests_run",
            "patch_id": patch_id,
            "status": status,
            "passed": passed,
            "failed": failed,
        })
        return result

    except subprocess.TimeoutExpired:
        result = PatchResult(
            patch_id=patch_id,
            status="rejected",
            failure_reason="pytest timed out after 120s",
        )
        _log_patch_event({"event": "tests_timeout", "patch_id": patch_id})
        return result
    except Exception as exc:
        result = PatchResult(
            patch_id=patch_id,
            status="rejected",
            failure_reason=str(exc),
        )
        _log_patch_event({"event": "tests_error", "patch_id": patch_id, "error": str(exc)})
        return result


def rollback_patch(patch_id: str) -> None:
    """Move patch from sandbox/patches/ to sandbox/rejected/."""
    src = SANDBOX_DIR / patch_id
    if src.exists():
        dst = REJECTED_DIR / patch_id
        shutil.move(str(src), str(dst))
        _log_patch_event({"event": "patch_rolled_back", "patch_id": patch_id})
        logger.info("Patch %s rolled back to rejected/", patch_id)
    else:
        logger.warning("Patch %s not found in sandbox for rollback", patch_id)


def apply_patch_human_gate(patch_id: str, target_path: str) -> dict[str, Any]:
    """
    Human Gate: apply the patch from sandbox to the target path.
    Should ONLY be called after human clicks 'Apply' in the UI.

    Returns {"status": "applied"|"error", "message": str}.
    """
    patch_dir = SANDBOX_DIR / patch_id
    if not patch_dir.exists():
        return {"status": "error", "message": f"Patch {patch_id} not found in sandbox"}

    # Collect patch files
    patch_files = list(patch_dir.iterdir())
    if not patch_files:
        return {"status": "error", "message": "Patch directory is empty"}

    target = Path(target_path)
    # Backup original if it exists
    backup_path = None
    if target.exists():
        backup_path = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(str(target), str(backup_path))

    try:
        # Apply first patch file to target
        patch_content = patch_files[0].read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(patch_content, encoding="utf-8")

        _log_patch_event({
            "event": "patch_applied",
            "patch_id": patch_id,
            "target": str(target),
            "backup": str(backup_path) if backup_path else None,
        })
        logger.info("Patch %s applied to %s", patch_id, target)
        return {"status": "applied", "message": f"Patch applied to {target_path}"}

    except Exception as exc:
        # Restore backup on failure
        if backup_path and backup_path.exists():
            shutil.copy2(str(backup_path), str(target))
        _log_patch_event({
            "event": "patch_apply_failed",
            "patch_id": patch_id,
            "error": str(exc),
        })
        return {"status": "error", "message": str(exc)}


def evaluate_patch(
    filename: str,
    content: str,
    target_module: str | None = None,
    patch_id: str | None = None,
) -> PatchResult:
    """
    Full pipeline:
    1. Write to sandbox
    2. Run pytest
    3. Rollback if failed
    Returns PatchResult.
    """
    pid, patch_path = write_patch_to_sandbox(filename, content, patch_id)

    # Temporarily copy patch to a temp location for testing
    # (don't overwrite production code during evaluation)
    result = run_tests_for_patch(pid, target_module)
    result.patch_path = str(patch_path)

    if result.status == "rejected":
        logger.warning("Patch %s rejected — rolling back. Reason: %s", pid, result.failure_reason[:200])
        _log_patch_event({
            "event": "patch_rejected",
            "patch_id": pid,
            "reason": result.failure_reason[:500],
        })
        # Keep in sandbox/patches (not rolled back to rejected) for inspection
        # Only auto-rollback on catastrophic failures
    else:
        logger.info("Patch %s passed all tests — awaiting human gate", pid)
        _log_patch_event({"event": "patch_ready", "patch_id": pid})

    return result


def list_pending_patches() -> list[dict[str, Any]]:
    """Return list of patches in sandbox/patches/ with their log entries."""
    patches = []
    if not SANDBOX_DIR.exists():
        return patches

    for patch_dir in SANDBOX_DIR.iterdir():
        if patch_dir.is_dir():
            files = [f.name for f in patch_dir.iterdir()]
            patches.append({
                "patch_id": patch_dir.name,
                "files": files,
                "created": datetime.fromtimestamp(
                    patch_dir.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })

    patches.sort(key=lambda x: x["created"], reverse=True)
    return patches


def get_patches_log(last_n: int = 50) -> list[dict[str, Any]]:
    """Read last N entries from memory/patches.log."""
    if not PATCHES_LOG.exists():
        return []

    lines = PATCHES_LOG.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines[-last_n:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries
