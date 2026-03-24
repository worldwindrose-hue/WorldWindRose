"""
ROSA OS — GitHub Repository Connector.
Reads public (and private with token) repos via GitHub REST API.
Ingests README, key .md/.py files into the knowledge graph.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any

import httpx

from core.config import get_settings

logger = logging.getLogger("rosa.integrations.github")

_PRIORITY_FILES = {
    "README.md", "README.rst", "README.txt", "readme.md",
    "ARCHITECTURE.md", "DESIGN.md", "CONTRIBUTING.md",
    "main.py", "app.py", "core/__init__.py", "setup.py",
    "pyproject.toml", "package.json",
}

_PRIORITY_EXTENSIONS = {".md", ".rst", ".py", ".ts", ".js", ".yaml", ".yml", ".toml"}


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL."""
    url = url.strip().rstrip("/")
    # https://github.com/owner/repo or github.com/owner/repo
    m = re.match(r"(?:https?://)?github\.com/([^/]+)/([^/\s?#]+)", url)
    if not m:
        raise ValueError(f"Cannot parse GitHub URL: {url!r}")
    return m.group(1), m.group(2).removesuffix(".git")


class GitHubConnector:
    """Read GitHub repos and ingest them into the ROSA knowledge graph."""

    BASE = "https://api.github.com"

    def __init__(self) -> None:
        self.token = get_settings().github_token

    def _headers(self) -> dict[str, str]:
        h = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ROSA-OS/4.0",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def get_repo_meta(self, owner: str, repo: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15, headers=self._headers()) as client:
            r = await client.get(f"{self.BASE}/repos/{owner}/{repo}")
            r.raise_for_status()
            d = r.json()
            return {
                "full_name": d.get("full_name"),
                "description": d.get("description") or "",
                "topics": d.get("topics", []),
                "stars": d.get("stargazers_count", 0),
                "language": d.get("language") or "",
                "default_branch": d.get("default_branch", "main"),
            }

    async def get_file_tree(self, owner: str, repo: str, branch: str = "main") -> list[str]:
        """Return list of file paths in the repo (recursive tree)."""
        async with httpx.AsyncClient(timeout=20, headers=self._headers()) as client:
            r = await client.get(
                f"{self.BASE}/repos/{owner}/{repo}/git/trees/{branch}",
                params={"recursive": "1"},
            )
            if r.status_code == 404:
                # Try HEAD commit reference
                r = await client.get(
                    f"{self.BASE}/repos/{owner}/{repo}/git/trees/HEAD",
                    params={"recursive": "1"},
                )
            r.raise_for_status()
            tree = r.json().get("tree", [])
        return [item["path"] for item in tree if item.get("type") == "blob"]

    def _select_files(self, paths: list[str], max_files: int) -> list[str]:
        """Pick the most informative files to ingest."""
        selected: list[str] = []
        # Priority 1: exact name matches
        for p in paths:
            fname = p.split("/")[-1]
            if fname in _PRIORITY_FILES and p not in selected:
                selected.append(p)
        # Priority 2: by extension, top-level or core/ directory
        for p in paths:
            if len(selected) >= max_files:
                break
            ext = "." + p.rsplit(".", 1)[-1] if "." in p else ""
            depth = p.count("/")
            if ext in _PRIORITY_EXTENSIONS and depth <= 2 and p not in selected:
                selected.append(p)
        return selected[:max_files]

    async def fetch_file_content(self, owner: str, repo: str, path: str) -> str | None:
        """Fetch a single file's content (decoded from base64)."""
        async with httpx.AsyncClient(timeout=15, headers=self._headers()) as client:
            r = await client.get(f"{self.BASE}/repos/{owner}/{repo}/contents/{path}")
            if r.status_code != 200:
                return None
            data = r.json()
            if data.get("encoding") == "base64":
                try:
                    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                except Exception:
                    return None
            return data.get("content")

    async def read_repo(self, url: str, max_files: int = 10) -> list[dict[str, Any]]:
        """Return list of {path, content, type} dicts for the most important files."""
        owner, repo = parse_github_url(url)
        meta = await self.get_repo_meta(owner, repo)
        branch = meta.get("default_branch", "main")

        paths = await self.get_file_tree(owner, repo, branch)
        selected = self._select_files(paths, max_files)

        files: list[dict[str, Any]] = []
        for path in selected:
            content = await self.fetch_file_content(owner, repo, path)
            if content:
                ext = path.rsplit(".", 1)[-1] if "." in path else "txt"
                files.append({"path": path, "content": content[:8000], "type": ext})

        return files

    async def ingest_to_graph(self, url: str, max_files: int = 10) -> dict[str, Any]:
        """Read repo files and push each into the knowledge graph."""
        from core.knowledge.graph import add_insight

        owner, repo = parse_github_url(url)
        meta = await self.get_repo_meta(owner, repo)
        files = await self.read_repo(url, max_files)

        total_nodes = 0
        total_edges = 0

        # First: ingest repo overview
        overview = (
            f"GitHub репозиторий {meta['full_name']}. "
            f"Описание: {meta['description']}. "
            f"Язык: {meta['language']}. "
            f"Звёзды: {meta['stars']}. "
            f"Темы: {', '.join(meta['topics'])}."
        )
        r = await add_insight(overview, {"source_type": "github", "repo": meta["full_name"]})
        total_nodes += r["nodes_created"]
        total_edges += r["edges_created"]

        # Then: ingest each file
        for f in files:
            text = f"Файл {f['path']} из {meta['full_name']}:\n\n{f['content'][:4000]}"
            r = await add_insight(text, {"source_type": "github", "repo": meta["full_name"], "file": f["path"]})
            total_nodes += r["nodes_created"]
            total_edges += r["edges_created"]

        return {
            "repo": meta["full_name"],
            "files_ingested": len(files),
            "nodes_created": total_nodes,
            "edges_created": total_edges,
            "meta": meta,
        }
