"""
ROSA OS — Tool implementations.
These classes are imported by hybrid_assistant.py and used by HybridRouter.
"""

from __future__ import annotations

import logging
import asyncio
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.tools")


class WebSearchTool:
    """
    Fetches and parses web pages.
    Uses httpx for HTTP requests and BeautifulSoup for HTML parsing.
    """

    def __init__(self) -> None:
        self._available = self._check_deps()

    def _check_deps(self) -> bool:
        try:
            import httpx
            from bs4 import BeautifulSoup
            return True
        except ImportError:
            logger.warning("WebSearchTool: httpx or beautifulsoup4 not installed")
            return False

    async def fetch(self, url: str, timeout: int = 15) -> str:
        """Fetch a URL and return cleaned text content."""
        if not self._available:
            return f"[WebSearchTool unavailable: missing dependencies]"
        try:
            import httpx
            from bs4 import BeautifulSoup

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(
                    url,
                    headers={"User-Agent": "ROSA-OS/1.0 (research assistant)"},
                )
                response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            # Remove script/style noise
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # Trim to reasonable size
            return text[:8000] if len(text) > 8000 else text

        except Exception as exc:
            logger.error("WebSearchTool.fetch failed for %s: %s", url, exc)
            return f"[Error fetching {url}: {exc}]"

    def fetch_sync(self, url: str) -> str:
        """Synchronous wrapper for fetch."""
        return asyncio.get_event_loop().run_until_complete(self.fetch(url))


class LocalKnowledgeBaseTool:
    """
    Reads local files from the knowledge base directory.
    Supports .txt, .md, .py, .json, and similar text files.
    """

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".csv", ".log"}
    MAX_FILE_SIZE = 512 * 1024  # 512 KB

    def __init__(self, kb_root: str = "memory") -> None:
        self.kb_root = Path(kb_root)
        self.kb_root.mkdir(parents=True, exist_ok=True)

    def read_file(self, path: str) -> str:
        """Read a local file. Path can be absolute or relative to kb_root."""
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = self.kb_root / path

        if not file_path.exists():
            return f"[File not found: {path}]"

        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return f"[Unsupported file type: {file_path.suffix}]"

        if file_path.stat().st_size > self.MAX_FILE_SIZE:
            return f"[File too large (>{self.MAX_FILE_SIZE // 1024}KB): {path}]"

        try:
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.error("LocalKnowledgeBaseTool.read_file failed for %s: %s", path, exc)
            return f"[Error reading {path}: {exc}]"

    def list_files(self, subdir: str = "") -> list[str]:
        """List files in the knowledge base (or a subdirectory)."""
        search_root = self.kb_root / subdir if subdir else self.kb_root
        if not search_root.exists():
            return []
        return [
            str(f.relative_to(self.kb_root))
            for f in search_root.rglob("*")
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]


class PersistentMemoryTool:
    """
    Persistent memory interface for Rosa.
    Thin wrapper around core/memory/store.py — delegates all storage to the async SQLite store.
    Falls back to in-memory list when the DB is not initialized (e.g. in CLI mode).
    """

    def __init__(self) -> None:
        self._fallback: list[dict[str, Any]] = []

    async def save(
        self,
        role: str,
        content: str,
        model_used: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Save a conversation turn."""
        try:
            from core.memory.store import get_store
            store = await get_store()
            await store.save_turn(role=role, content=content, model_used=model_used, session_id=session_id)
        except Exception as exc:
            logger.debug("PersistentMemoryTool falling back to in-memory: %s", exc)
            self._fallback.append({"role": role, "content": content})

    async def get_recent(self, limit: int = 20, session_id: str | None = None) -> list[dict[str, Any]]:
        """Retrieve recent conversation turns."""
        try:
            from core.memory.store import get_store
            store = await get_store()
            turns = await store.list_turns(session_id=session_id, limit=limit)
            return [{"role": t.role, "content": t.content} for t in reversed(turns)]
        except Exception:
            return self._fallback[-limit:]

    def save_sync(self, role: str, content: str, **kwargs: Any) -> None:
        """Synchronous save for use in non-async contexts."""
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self.save(role, content, **kwargs))
        except RuntimeError:
            # No running event loop — use fallback
            self._fallback.append({"role": role, "content": content})
