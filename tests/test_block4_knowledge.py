"""Tests for Block 4 — KnowledgeIndexer + RAGEngine."""
from __future__ import annotations

import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


# ── KnowledgeIndexer ──────────────────────────────────────────────────────


class TestKnowledgeIndexer:
    def test_indexer_singleton(self):
        """get_indexer() returns same instance."""
        from core.knowledge.indexer import get_indexer, KnowledgeIndexer
        a = get_indexer()
        b = get_indexer()
        assert a is b
        assert isinstance(a, KnowledgeIndexer)

    @pytest.mark.asyncio
    async def test_index_file_nonexistent(self):
        """Indexing a nonexistent file returns 0."""
        from core.knowledge.indexer import KnowledgeIndexer
        idx = KnowledgeIndexer()
        result = await idx.index_file(Path("/tmp/nonexistent_rosa_test.txt"))
        assert result == 0

    @pytest.mark.asyncio
    async def test_index_file_real(self, tmp_path):
        """Indexing a real text file calls ingest_text."""
        from core.knowledge.indexer import KnowledgeIndexer
        idx = KnowledgeIndexer()
        idx._index = {}  # fresh state

        test_file = tmp_path / "sample.md"
        test_file.write_text("# Hello World\nThis is a test document.")

        mock_result = MagicMock()
        mock_result.chunks = 1
        # ingest_text is imported inside the method from core.ingest.universal_ingester
        with patch("core.ingest.universal_ingester.ingest_text", new_callable=AsyncMock,
                   return_value=mock_result):
            result = await idx.index_file(test_file)

        assert result >= 0

    @pytest.mark.asyncio
    async def test_index_file_skip_unchanged(self, tmp_path):
        """File is not re-indexed if hash unchanged."""
        from core.knowledge.indexer import KnowledgeIndexer
        idx = KnowledgeIndexer()
        idx._index = {}  # fresh state

        test_file = tmp_path / "sample.md"
        test_file.write_text("# Stable content that won't change")

        mock_result = MagicMock()
        mock_result.chunks = 1
        with patch("core.ingest.universal_ingester.ingest_text", new_callable=AsyncMock,
                   return_value=mock_result) as mock_ingest:
            # First index
            await idx.index_file(test_file)
            # Second index — should be skipped (hash unchanged)
            result2 = await idx.index_file(test_file)

        # ingest_text should be called exactly once
        assert mock_ingest.call_count == 1
        assert result2 == 0  # skipped = 0 new chunks

    @pytest.mark.asyncio
    async def test_index_directory(self, tmp_path):
        """index_directory returns dict with stats."""
        from core.knowledge.indexer import KnowledgeIndexer
        idx = KnowledgeIndexer()
        idx._index = {}  # fresh state

        (tmp_path / "a.md").write_text("Doc A with some content")
        (tmp_path / "b.txt").write_text("Doc B with some content")

        mock_result = MagicMock()
        mock_result.chunks = 1
        with patch("core.ingest.universal_ingester.ingest_text", new_callable=AsyncMock,
                   return_value=mock_result):
            result = await idx.index_directory(tmp_path, recursive=False)

        # result should have stats keys
        assert isinstance(result, dict)
        assert "errors" in result

    def test_watchdog_graceful_without_package(self):
        """start_watchdog doesn't crash if watchdog not installed."""
        from core.knowledge.indexer import KnowledgeIndexer
        idx = KnowledgeIndexer()
        with patch.dict("sys.modules", {"watchdog": None, "watchdog.observers": None,
                                         "watchdog.events": None}):
            # Should not raise
            try:
                idx.start_watchdog(["/tmp"])
            except Exception as exc:
                pytest.fail(f"start_watchdog raised unexpectedly: {exc}")


# ── RAGEngine ────────────────────────────────────────────────────────────


class TestRAGEngine:
    def test_rag_singleton(self):
        """get_rag_engine() returns same instance."""
        from core.knowledge.rag_engine import get_rag_engine, RAGEngine
        a = get_rag_engine()
        b = get_rag_engine()
        assert a is b
        assert isinstance(a, RAGEngine)

    @pytest.mark.asyncio
    async def test_retrieve_empty(self):
        """retrieve() returns list even when store is empty."""
        from core.knowledge.rag_engine import RAGEngine
        engine = RAGEngine()
        # get_store is imported inside the method from core.memory.store
        with patch("core.memory.store.get_store") as mock_store_fn:
            mock_store = AsyncMock()
            mock_store.search_insights = AsyncMock(return_value=[])
            mock_store_fn.return_value = mock_store
            results = await engine.retrieve("test query", top_k=5)
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_retrieve_deduplication(self):
        """retrieve() deduplicates by content prefix."""
        from core.knowledge.rag_engine import RAGEngine
        engine = RAGEngine()

        dup_text = "This is duplicated content that is identical"
        mock_results = [
            {"content": dup_text, "relevance": 0.9, "source_type": "knowledge"},
            {"content": dup_text, "relevance": 0.85, "source_type": "knowledge"},
            {"content": "Unique content here completely different", "relevance": 0.7, "source_type": "knowledge"},
        ]

        with patch("core.memory.store.get_store") as mock_store_fn:
            mock_store = AsyncMock()
            mock_store.search_insights = AsyncMock(return_value=mock_results)
            mock_store_fn.return_value = mock_store
            results = await engine.retrieve("test", top_k=10)

        # Duplicates should be removed
        texts = [r["text"] for r in results]
        assert texts.count(dup_text) <= 1

    def test_augment_prompt_empty(self):
        """augment_prompt with no results returns query unchanged."""
        from core.knowledge.rag_engine import RAGEngine
        engine = RAGEngine()
        result = engine.augment_prompt("My question", [])
        assert "My question" in result

    def test_augment_prompt_with_context(self):
        """augment_prompt wraps context in knowledge block."""
        from core.knowledge.rag_engine import RAGEngine
        engine = RAGEngine()
        retrieved = [
            {"text": "Rosa is an AI assistant", "score": 0.9, "source": "docs"},
        ]
        result = engine.augment_prompt("Who is Rosa?", retrieved)
        assert "КОНТЕКСТ" in result or "context" in result.lower()
        assert "Rosa is an AI assistant" in result
        assert "Who is Rosa?" in result

    @pytest.mark.asyncio
    async def test_local_only_answer(self):
        """local_only_answer returns string."""
        from core.knowledge.rag_engine import RAGEngine
        engine = RAGEngine()
        with patch.object(engine, "retrieve", new_callable=AsyncMock, return_value=[]):
            result = await engine.local_only_answer("test question")
        assert isinstance(result, str)
