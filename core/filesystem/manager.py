"""
ROSA OS — Filesystem Manager (Phase 2).

Provides sandboxed file system access to allowed zones only.
Denied zones: /System, /usr, ~/.ssh, ~/.aws, and others.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.filesystem")

# Allowed read/write zones (expanduser applied at runtime)
_ALLOWED_ZONES = [
    "~/Desktop/Rosa_Assistant/",
    "~/Documents/",
    "~/Downloads/",
    "~/Desktop/",
]

# Explicitly denied zones — checked before allowed
_DENIED_PATTERNS = [
    r"^/System",
    r"^/usr",
    r"^/bin",
    r"^/sbin",
    r"^/etc",
    r"^/var/db",
    r"/\.ssh",
    r"/\.aws",
    r"/\.gnupg",
    r"/keychain",
]

# Read-only zones (can read but not write)
_READ_ONLY_ZONES = [
    "~/Downloads/",
    "~/Desktop/",
]


def _expand(path: str | Path) -> Path:
    return Path(os.path.expanduser(str(path))).resolve()


def _is_denied(path: Path) -> bool:
    s = str(path)
    for pat in _DENIED_PATTERNS:
        if re.search(pat, s):
            return True
    return False


def _is_allowed(path: Path) -> bool:
    if _is_denied(path):
        return False
    for zone in _ALLOWED_ZONES:
        if str(path).startswith(str(_expand(zone))):
            return True
    return False


def _is_write_allowed(path: Path) -> bool:
    if _is_denied(path):
        return False
    for zone in _READ_ONLY_ZONES:
        if str(path).startswith(str(_expand(zone))):
            return False
    for zone in _ALLOWED_ZONES:
        if str(path).startswith(str(_expand(zone))):
            return True
    return False


class FileSystemManager:
    """Sandboxed file system operations."""

    def read_file(self, path: str | Path) -> str:
        """Read a file from an allowed zone."""
        p = _expand(path)
        if not _is_allowed(p):
            raise PermissionError(f"Access denied: {p}")
        if not p.exists():
            raise FileNotFoundError(f"File not found: {p}")
        return p.read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str | Path, content: str) -> dict[str, Any]:
        """Write content to a file in an allowed writable zone."""
        p = _expand(path)
        if not _is_write_allowed(p):
            raise PermissionError(f"Write access denied: {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        logger.info("Wrote %d bytes to %s", len(content), p)
        return {"success": True, "path": str(p), "bytes": len(content)}

    def list_dir(self, path: str | Path) -> list[dict[str, Any]]:
        """List directory contents (allowed zones only)."""
        p = _expand(path)
        if not _is_allowed(p):
            raise PermissionError(f"Access denied: {p}")
        if not p.is_dir():
            raise NotADirectoryError(f"Not a directory: {p}")
        items = []
        for entry in sorted(p.iterdir()):
            try:
                stat = entry.stat()
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": "dir" if entry.is_dir() else "file",
                    "size": stat.st_size if entry.is_file() else 0,
                    "modified": stat.st_mtime,
                })
            except Exception:
                pass
        return items

    def search_files(
        self,
        query: str,
        root: str | Path | None = None,
        extensions: list[str] | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Search files by name or content in allowed zones."""
        root_path = _expand(root) if root else _expand("~/Desktop/Rosa_Assistant/")
        if not _is_allowed(root_path):
            raise PermissionError(f"Access denied: {root_path}")

        results = []
        q_lower = query.lower()
        exts = set(extensions) if extensions else None

        for p in root_path.rglob("*"):
            if not p.is_file():
                continue
            if exts and p.suffix not in exts:
                continue
            try:
                if q_lower in p.name.lower():
                    results.append({
                        "path": str(p),
                        "name": p.name,
                        "match_type": "name",
                        "size": p.stat().st_size,
                    })
                elif q_lower in p.read_text(encoding="utf-8", errors="replace").lower():
                    results.append({
                        "path": str(p),
                        "name": p.name,
                        "match_type": "content",
                        "size": p.stat().st_size,
                    })
            except Exception:
                pass
            if len(results) >= max_results:
                break
        return results

    def get_file_tree(self, root: str | Path | None = None, depth: int = 3) -> dict[str, Any]:
        """Return a tree structure of a directory."""
        root_path = _expand(root) if root else _expand("~/Desktop/Rosa_Assistant/")
        if not _is_allowed(root_path):
            raise PermissionError(f"Access denied: {root_path}")

        def _build(p: Path, current_depth: int) -> dict:
            node: dict[str, Any] = {"name": p.name, "path": str(p)}
            if p.is_dir() and current_depth > 0:
                children = []
                try:
                    for child in sorted(p.iterdir()):
                        if child.name.startswith(".") or child.name == "__pycache__":
                            continue
                        children.append(_build(child, current_depth - 1))
                except PermissionError:
                    pass
                node["type"] = "dir"
                node["children"] = children
            else:
                node["type"] = "file"
                try:
                    node["size"] = p.stat().st_size
                except Exception:
                    node["size"] = 0
            return node

        return _build(root_path, depth)

    def allowed_zones(self) -> list[str]:
        return [str(_expand(z)) for z in _ALLOWED_ZONES]


# Singleton
_fs_manager: FileSystemManager | None = None


def get_fs_manager() -> FileSystemManager:
    global _fs_manager
    if _fs_manager is None:
        _fs_manager = FileSystemManager()
    return _fs_manager
