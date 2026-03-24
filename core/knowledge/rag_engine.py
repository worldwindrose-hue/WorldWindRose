"""ROSA OS — RAG Engine. Retrieval-Augmented Generation with local-only mode."""

from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger("rosa.knowledge.rag")


class RAGEngine:
    async def retrieve(self, query: str, sources: list[str] = None, top_k: int = 10) -> list[dict]:
        results = []
        # Search SQLite knowledge graph
        try:
            from core.memory.store import get_store
            store = await get_store()
            hits = await store.search_insights(query, limit=top_k)
            for h in hits:
                results.append({
                    "text": h.get("content", ""),
                    "score": h.get("relevance", 0.5),
                    "source": h.get("source_type", "knowledge"),
                    "metadata": h,
                })
        except Exception as exc:
            logger.debug("SQLite RAG search failed: %s", exc)

        # Search ChromaDB episodic memory
        try:
            from core.memory.eternal import get_eternal_memory
            mem = get_eternal_memory()
            ep_results = await mem.episodic.search(query, top_k=top_k)
            for r in ep_results:
                results.append({
                    "text": r.get("text", ""),
                    "score": r.get("score", 0.5),
                    "source": "episodic",
                    "metadata": r.get("metadata", {}),
                })
        except Exception:
            pass

        # Deduplicate by text prefix
        seen: set[str] = set()
        unique = []
        for r in results:
            key = r["text"][:100]
            if key not in seen and r["text"].strip():
                seen.add(key)
                unique.append(r)

        # Sort by score descending
        unique.sort(key=lambda x: x.get("score", 0), reverse=True)
        return unique[:top_k]

    def augment_prompt(self, query: str, retrieved: list[dict]) -> str:
        if not retrieved:
            return query
        context_parts = []
        for i, r in enumerate(retrieved[:7], 1):
            text = r["text"][:400].strip()
            if text:
                context_parts.append(f"{i}. {text}")
        context = "\n".join(context_parts)
        return (
            f"[КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ]\n{context}\n[/КОНТЕКСТ]\n\n"
            f"Используй этот контекст если он релевантен вопросу.\n\n{query}"
        )

    async def local_only_answer(self, query: str) -> str:
        retrieved = await self.retrieve(query, top_k=5)
        if not retrieved:
            return f"В локальной базе знаний нет информации по запросу: {query}"
        context = "\n\n".join(r["text"][:300] for r in retrieved if r["text"].strip())
        return f"На основе локальной базы знаний:\n\n{context}"


_rag: Optional[RAGEngine] = None


def get_rag_engine() -> RAGEngine:
    global _rag
    if _rag is None:
        _rag = RAGEngine()
    return _rag
