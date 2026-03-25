"""
ROSA OS — Eternal Hybrid Memory (3-layer architecture).
Layer 1: Working memory (session context, deque-based)
Layer 2: Episodic memory (ChromaDB vectors, SQLite fallback)
Layer 3: Knowledge graph memory (entity/relation triples)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.memory.eternal")

# ── LAYER 1: Working Memory ──────────────────────────────────────────────────

class WorkingMemory:
    """Short-term session memory using a bounded deque."""

    def __init__(self, max_messages: int = 100, max_tokens: int = 8000):
        self.max_messages = max_messages
        self.max_tokens = max_tokens
        self._messages: deque[dict] = deque(maxlen=max_messages)
        self._token_count: int = 0

    def add(self, role: str, content: str) -> None:
        """Add a message to working memory."""
        msg = {"role": role, "content": content}
        self._messages.append(msg)
        # rough token estimate: ~4 chars per token
        self._token_count = sum(len(m["content"]) // 4 for m in self._messages)

    def get_messages(self) -> list[dict]:
        return list(self._messages)

    def needs_compression(self) -> bool:
        return self._token_count > self.max_tokens or len(self._messages) >= self.max_messages

    async def compress(self) -> str:
        """Summarize working memory via Kimi and return summary string."""
        if not self._messages:
            return ""
        try:
            from core.config import get_settings
            import httpx
            settings = get_settings()
            if not settings.openrouter_api_key:
                return f"[{len(self._messages)} messages compressed]"
            text = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in list(self._messages)[-20:])
            payload = {
                "model": settings.cloud_model,
                "messages": [
                    {"role": "system", "content": "Summarize this conversation in 3-5 sentences. Be concise."},
                    {"role": "user", "content": text},
                ],
                "max_tokens": 300,
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                    json=payload,
                )
                summary = resp.json()["choices"][0]["message"]["content"]
            # Keep only last 10 messages after compression
            recent = list(self._messages)[-10:]
            self._messages.clear()
            self._messages.extend(recent)
            self._token_count = sum(len(m["content"]) // 4 for m in self._messages)
            return summary
        except Exception as exc:
            logger.warning("Working memory compression failed: %s", exc)
            # Fallback: truncate to last 20 messages
            recent = list(self._messages)[-20:]
            self._messages.clear()
            self._messages.extend(recent)
            return f"[{len(recent)} recent messages retained]"


# ── LAYER 2: Episodic Memory ──────────────────────────────────────────────────

class EpisodicMemory:
    """Vector memory using ChromaDB with SQLite fallback."""

    def __init__(self):
        self._chroma_client = None
        self._collection = None
        self._chroma_available = False
        self._embedder = None
        self._embedder_available = False

    def _ensure_chroma(self) -> bool:
        if self._chroma_available:
            return True
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
            memory_dir = Path("memory/chroma")
            memory_dir.mkdir(parents=True, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(
                path=str(memory_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = self._chroma_client.get_or_create_collection("rosa_episodic")
            self._chroma_available = True
            return True
        except Exception as exc:
            logger.debug("ChromaDB not available, using SQLite fallback: %s", exc)
            return False

    def _get_embedding(self, text: str) -> list[float] | None:
        try:
            if self._embedder is None:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                self._embedder_available = True
            return self._embedder.encode(text).tolist()
        except Exception:
            self._embedder_available = False
            return None

    async def add(self, text: str, source: str = "chat", tags: list[str] | None = None, metadata: dict | None = None) -> None:
        """Add an episodic memory entry."""
        import uuid as _uuid
        entry_id = str(_uuid.uuid4())
        meta = metadata or {}
        meta.update({"source": source, "tags": json.dumps(tags or []), "ts": datetime.now(timezone.utc).isoformat()})

        if self._ensure_chroma():
            try:
                embedding = self._get_embedding(text)
                kwargs: dict[str, Any] = {"ids": [entry_id], "documents": [text[:2000]], "metadatas": [meta]}
                if embedding:
                    kwargs["embeddings"] = [embedding]
                self._collection.add(**kwargs)
                return
            except Exception as exc:
                logger.warning("ChromaDB add failed: %s", exc)

        # Fallback: SQLite via store
        try:
            from core.memory.store import get_store
            store = await get_store()
            node = await store.create_node(
                title=text[:200],
                type="episodic",
                summary=text[:1000],
                source_type=source,
            )
            logger.debug("Episodic memory saved to SQLite node: %s", node.id)
        except Exception as exc:
            logger.warning("SQLite episodic fallback failed: %s", exc)

    async def search(self, query: str, top_k: int = 7) -> list[dict]:
        """Search episodic memory by semantic similarity."""
        if self._ensure_chroma() and self._collection:
            try:
                kwargs: dict[str, Any] = {"query_texts": [query], "n_results": min(top_k, max(1, self._collection.count()))}
                if self._embedder_available:
                    emb = self._get_embedding(query)
                    if emb:
                        kwargs = {"query_embeddings": [emb], "n_results": kwargs["n_results"]}
                results = self._collection.query(**kwargs)
                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]
                return [
                    {"text": doc, "score": 1.0 - (dist / 2.0), "metadata": meta}
                    for doc, meta, dist in zip(docs, metas, distances)
                ]
            except Exception as exc:
                logger.warning("ChromaDB search failed: %s", exc)

        # Fallback: SQLite fulltext search
        try:
            from core.memory.store import get_store
            store = await get_store()
            nodes = await store.search_nodes(query, limit=top_k)
            return [
                {"text": n.summary or n.title, "score": 0.5, "metadata": {"source": n.source_type, "ts": n.created_at.isoformat()}}
                for n in nodes
            ]
        except Exception as exc:
            logger.warning("SQLite episodic search failed: %s", exc)
            return []

    async def delete(self, entry_id: str) -> bool:
        """Remove an entry from episodic memory."""
        if self._ensure_chroma() and self._collection:
            try:
                self._collection.delete(ids=[entry_id])
                return True
            except Exception as exc:
                logger.warning("ChromaDB delete failed: %s", exc)
        return False

    async def stats(self) -> dict:
        count = 0
        backend = "sqlite"
        if self._ensure_chroma() and self._collection:
            try:
                count = self._collection.count()
                backend = "chromadb"
            except Exception:
                pass
        if backend == "sqlite":
            try:
                from core.memory.store import get_store
                store = await get_store()
                nodes = await store.list_nodes(type="episodic", limit=10000)
                count = len(nodes)
            except Exception:
                pass
        return {"count": count, "backend": backend}


# ── LAYER 3: Graph Memory ──────────────────────────────────────────────────────

class GraphMemory:
    """Knowledge graph storing subject-predicate-object triples."""

    async def add_fact(self, subject: str, predicate: str, obj: str, source: str = "") -> None:
        """Add a fact triple to the knowledge graph."""
        try:
            from core.memory.store import get_store
            store = await get_store()
            # Create/reuse nodes for subject and object
            subj_nodes = await store.search_nodes(subject, limit=1)
            if subj_nodes and subj_nodes[0].title.lower() == subject.lower():
                subj_node = subj_nodes[0]
            else:
                subj_node = await store.create_node(title=subject, type="entity", source_type=source or "graph")

            obj_nodes = await store.search_nodes(obj, limit=1)
            if obj_nodes and obj_nodes[0].title.lower() == obj.lower():
                obj_node = obj_nodes[0]
            else:
                obj_node = await store.create_node(title=obj, type="entity", source_type=source or "graph")

            await store.create_edge(
                from_node_id=str(subj_node.id),
                to_node_id=str(obj_node.id),
                relation_type=predicate,
            )
        except Exception as exc:
            logger.warning("GraphMemory.add_fact failed: %s", exc)

    async def query(self, query_text: str, max_hops: int = 2) -> list[dict]:
        """Query the graph for entities related to query_text."""
        try:
            from core.memory.store import get_store
            store = await get_store()
            nodes = await store.search_nodes(query_text, limit=10)
            results = []
            for node in nodes:
                edges = await store.list_edges(node_id=str(node.id), limit=20)
                for edge in edges:
                    results.append({
                        "subject": str(node.id),
                        "subject_title": node.title,
                        "predicate": edge.relation_type,
                        "object": str(edge.to_node_id if str(edge.from_node_id) == str(node.id) else edge.from_node_id),
                    })
            return results[:max_hops * 10]
        except Exception as exc:
            logger.warning("GraphMemory.query failed: %s", exc)
            return []

    async def extract_and_add(self, text: str, source: str = "") -> None:
        """Extract entities from text using Kimi and add to graph."""
        try:
            from core.config import get_settings
            import httpx
            settings = get_settings()
            if not settings.openrouter_api_key:
                return
            payload = {
                "model": settings.cloud_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract 3-5 key facts from this text as JSON array of "
                            "[{subject, predicate, object}] triples. Return only valid JSON."
                        ),
                    },
                    {"role": "user", "content": text[:1000]},
                ],
                "max_tokens": 400,
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                    json=payload,
                )
            raw = resp.json()["choices"][0]["message"]["content"]
            # Strip markdown fences if present
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            triples = json.loads(raw.strip())
            for triple in triples[:5]:
                subj = triple.get("subject", "")
                pred = triple.get("predicate", "related_to")
                obj = triple.get("object", "")
                if subj and obj:
                    await self.add_fact(subj, pred, obj, source=source)
        except Exception as exc:
            logger.debug("Entity extraction failed (non-critical): %s", exc)


# ── Session Context ──────────────────────────────────────────────────────────

class SessionContext:
    """Persistent session context stored in SQLite."""

    _cache: dict = {}

    async def load(self) -> dict:
        try:
            ctx_path = Path("memory/session_context.json")
            if ctx_path.exists():
                data = json.loads(ctx_path.read_text())
                self._cache = data
                return data
        except Exception as exc:
            logger.warning("SessionContext.load failed: %s", exc)
        return {}

    async def save(self, context: dict) -> None:
        try:
            self._cache.update(context)
            ctx_path = Path("memory/session_context.json")
            ctx_path.parent.mkdir(parents=True, exist_ok=True)
            ctx_path.write_text(json.dumps(self._cache, ensure_ascii=False, indent=2))
        except Exception as exc:
            logger.warning("SessionContext.save failed: %s", exc)

    async def update(self, key: str, value: Any) -> None:
        self._cache[key] = value
        await self.save(self._cache)

    async def get_summary(self) -> str:
        data = await self.load()
        if not data:
            return "Нет сохранённого контекста."
        parts = []
        for k, v in list(data.items())[:5]:
            parts.append(f"{k}: {str(v)[:100]}")
        return "\n".join(parts)


# ── Main EternalMemory Manager ───────────────────────────────────────────────

class EternalMemory:
    """Unified 3-layer memory manager."""

    def __init__(self):
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory()
        self.graph = GraphMemory()
        self.context = SessionContext()

    async def remember(self, role: str, content: str, source: str = "chat", importance: float = 0.5) -> None:
        """Add to all relevant memory layers."""
        # Layer 1: always
        self.working.add(role, content)

        # Layer 2: episodic for important content
        if importance >= 0.3:
            asyncio.create_task(self.episodic.add(content, source=source, tags=[role]))

        # Layer 3: extract entities for high-importance
        if importance >= 0.7:
            asyncio.create_task(self.graph.extract_and_add(content, source=source))

        # Compress working memory if needed
        if self.working.needs_compression():
            try:
                summary = await self.working.compress()
                if summary:
                    await self.episodic.add(summary, source="compression", tags=["summary"])
            except Exception as exc:
                logger.warning("Auto-compression failed: %s", exc)

    async def recall(self, query: str) -> dict:
        """Recall from all layers."""
        results: dict[str, Any] = {}

        # Layer 1: working memory
        results["working"] = self.working.get_messages()[-10:]

        # Layer 2: episodic search
        try:
            results["episodic"] = await self.episodic.search(query, top_k=5)
        except Exception:
            results["episodic"] = []

        # Layer 3: graph query
        try:
            results["graph"] = await self.graph.query(query)
        except Exception:
            results["graph"] = []

        # Session context
        try:
            results["context"] = await self.context.load()
        except Exception:
            results["context"] = {}

        return results

    async def stats(self) -> dict:
        episodic_stats = await self.episodic.stats()
        return {
            "working_messages": len(self.working.get_messages()),
            "working_needs_compression": self.working.needs_compression(),
            "episodic": episodic_stats,
            "context_keys": len(self._load_context_cache()),
        }

    def _load_context_cache(self) -> dict:
        try:
            ctx_path = Path("memory/session_context.json")
            if ctx_path.exists():
                return json.loads(ctx_path.read_text())
        except Exception:
            pass
        return {}


# ── Singleton ────────────────────────────────────────────────────────────────

_eternal_memory_instance: EternalMemory | None = None


def get_eternal_memory() -> EternalMemory:
    global _eternal_memory_instance
    if _eternal_memory_instance is None:
        _eternal_memory_instance = EternalMemory()
    return _eternal_memory_instance
