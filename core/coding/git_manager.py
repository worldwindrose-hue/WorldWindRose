"""
ROSA OS — Git Manager (Phase 7).

Rosa can read git history, create branches, and auto-commit.
Write operations require explicit calls (no auto-commit on reads).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.coding.git")

_REPO_ROOT = Path(__file__).parent.parent.parent  # project root


def _git(*args: str) -> str:
    """Run a git command and return output."""
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), *args],
            capture_output=True, text=True, timeout=30,
        )
        return (result.stdout + result.stderr).strip()
    except Exception as exc:
        return f"git error: {exc}"


class GitManager:
    """Git operations for Rosa's self-development."""

    def get_diff(self, staged: bool = False) -> str:
        if staged:
            return _git("diff", "--staged")
        return _git("diff")

    def get_log(self, limit: int = 10) -> list[dict[str, Any]]:
        out = _git("log", f"--max-count={limit}", "--format=%H|%s|%an|%ar")
        if not out or "git error" in out:
            return []
        entries = []
        for line in out.splitlines():
            parts = line.split("|", 3)
            if len(parts) >= 4:
                entries.append({
                    "hash": parts[0][:8],
                    "subject": parts[1],
                    "author": parts[2],
                    "ago": parts[3],
                })
        return entries

    def get_status(self) -> str:
        return _git("status", "--short")

    def get_current_branch(self) -> str:
        return _git("rev-parse", "--abbrev-ref", "HEAD")

    def create_branch(self, name: str) -> str:
        return _git("checkout", "-b", name)

    def auto_commit(self, message: str, files: list[str] | None = None) -> dict[str, Any]:
        """Stage files and create a commit."""
        if files:
            for f in files:
                _git("add", f)
        else:
            _git("add", "-A")

        result = _git("commit", "-m", message)
        success = "nothing to commit" not in result and "error" not in result.lower()
        return {"success": success, "output": result}

    def get_changed_files(self) -> list[str]:
        out = _git("diff", "--name-only", "HEAD")
        return [f.strip() for f in out.splitlines() if f.strip()]

    def stash(self) -> str:
        return _git("stash")

    def pop_stash(self) -> str:
        return _git("stash", "pop")


_git_manager: GitManager | None = None


def get_git_manager() -> GitManager:
    global _git_manager
    if _git_manager is None:
        _git_manager = GitManager()
    return _git_manager
