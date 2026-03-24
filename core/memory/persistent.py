"""
ROSA OS — Persistent Memory Layers (Phase 3).

Three layers:
1. WORKING  — last 50 messages in-memory (fast)
2. EPISODIC — vector embeddings via ChromaDB (or SQLite fallback)
3. SEMANTIC — facts/concepts extracted from dialogs → Knowledge Graph

MemoryInjector: injects relevant memories into every LLM call.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.memory.persistent")

# ── Working memory ────────────────────────────────────────────────────────────

@dataclass
class WorkingMessage:
    role: str       # "user" | "assistant"
    content: str
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkingMemory:
    """In-memory ring buffer of last N messages."""

    def __init__(self, capacity: int = 50) -> None:
        self._buf: deque[WorkingMessage] = deque(maxlen=capacity)

    def add(self, role: str, content: str) -> None:
        self._buf.append(WorkingMessage(role=role, content=content))

    def get_recent(self, n: int = 10) -> list[WorkingMessage]:
        items = list(self._buf)
        return items[-n:]

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)


# ── Episodic memory (vector search) ──────────────────────────────────────────

class EpisodicMemory:
    """
    Semantic vector storage via ChromaDB.
    Falls back to keyword search in SQLite knowledge_nodes if ChromaDB unavailable.
    """

    def __init__(self) -> None:
        self._chroma_available = False
        self._collection = None
        self._try_init_chroma()

    def _try_init_chroma(self) -> None:
        try:
            import chromadb  # noqa: F401
            self._chroma_available = True
            logger.info("ChromaDB available — episodic memory enabled")
        except ImportError:
            logger.info("ChromaDB not installed — using SQLite fallback for episodic memory")

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
            from pathlib import Path
            client = chromadb.PersistentClient(path=str(Path("memory/chroma")))
            self._collection = client.get_or_create_collection(
                "rosa_episodic",
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection
        except Exception as exc:
            logger.debug("ChromaDB collection init failed: %s", exc)
            return None

    def add(self, text: str, metadata: dict | None = None, doc_id: str | None = None) -> bool:
        """Add a text to episodic memory."""
        if not self._chroma_available:
            return False
        col = self._get_collection()
        if col is None:
            return False
        import uuid
        try:
            col.add(
                documents=[text],
                metadatas=[metadata or {}],
                ids=[doc_id or str(uuid.uuid4())],
            )
            return True
        except Exception as exc:
            logger.debug("ChromaDB add failed: %s", exc)
            return False

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search in episodic memory."""
        if self._chroma_available:
            col = self._get_collection()
            if col:
                try:
                    results = col.query(query_texts=[query], n_results=top_k)
                    docs = results.get("documents", [[]])[0]
                    metas = results.get("metadatas", [[]])[0]
                    return [{"text": d, "metadata": m} for d, m in zip(docs, metas)]
                except Exception as exc:
                    logger.debug("ChromaDB search failed: %s", exc)

        # SQLite fallback
        return await self._sqlite_search(query, top_k)

    async def _sqlite_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        try:
            from core.memory.store import get_store
            store = await get_store()
            nodes = await store.search_nodes(query=query, limit=top_k)
            return [
                {"text": getattr(n, "title", ""), "metadata": {"source": "knowledge_node"}}
                for n in nodes
            ]
        except Exception:
            return []


# ── Semantic memory (knowledge graph) ────────────────────────────────────────

class SemanticMemory:
    """Extract facts from dialog turns and store in knowledge graph."""

    _EXTRACT_PROMPT = """Из этого диалога извлеки конкретные факты, концепты и сущности.
Формат JSON: {{"facts": ["факт 1", "факт 2", ...]}}
Диалог:
{dialog}"""

    async def extract_and_store(self, dialog: str, session_id: str = "memory") -> list[str]:
        """Extract facts from dialog and add to knowledge graph."""
        facts = await self._extract_facts(dialog)
        if facts:
            await self._store_facts(facts, session_id)
        return facts

    async def _extract_facts(self, dialog: str) -> list[str]:
        try:
            from openai import AsyncOpenAI
            from core.config import get_settings
            settings = get_settings()
            client = AsyncOpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            )
            resp = await client.chat.completions.create(
                model=settings.default_model,
                messages=[{"role": "user", "content": self._EXTRACT_PROMPT.format(dialog=dialog[:2000])}],
                max_tokens=512,
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            return data.get("facts", [])
        except Exception as exc:
            logger.debug("Fact extraction failed: %s", exc)
            return []

    async def _store_facts(self, facts: list[str], session_id: str) -> None:
        try:
            from core.knowledge.graph import add_insight
            for fact in facts[:10]:
                await add_insight(
                    text=fact,
                    metadata={"source": "dialog_extraction", "session_id": session_id},
                    session_id=session_id,
                )
        except Exception as exc:
            logger.debug("Fact storage failed: %s", exc)


# ── Memory Injector ───────────────────────────────────────────────────────────

class MemoryInjector:
    """
    Injects relevant memories into every LLM prompt.
    Searches both episodic and semantic memory.
    """

    def __init__(self) -> None:
        self.episodic = EpisodicMemory()
        self.semantic = SemanticMemory()

    async def build_memory_context(self, query: str, top_k: int = 5) -> str:
        """Return a memory injection string for the system prompt."""
        results = await self.episodic.search(query, top_k=top_k)
        if not results:
            return ""
        lines = ["Из моей памяти (релевантные воспоминания):"]
        for r in results:
            text = r.get("text", "").strip()
            if text:
                lines.append(f"  • {text[:200]}")
        return "\n".join(lines)

    async def remember(self, role: str, content: str, session_id: str = "chat") -> None:
        """Store a message in episodic memory."""
        self.episodic.add(
            text=f"{role}: {content}",
            metadata={"role": role, "session_id": session_id},
        )


# ── Singletons ────────────────────────────────────────────────────────────────

_working = WorkingMemory()
_injector: MemoryInjector | None = None


def get_working_memory() -> WorkingMemory:
    return _working


def get_memory_injector() -> MemoryInjector:
    global _injector
    if _injector is None:
        _injector = MemoryInjector()
    return _injector
