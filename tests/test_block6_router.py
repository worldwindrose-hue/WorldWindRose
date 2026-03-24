"""Tests for Block 6 — LocalRouter + CacheManager."""
from __future__ import annotations

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch


# ── CacheManager ──────────────────────────────────────────────────────────


class TestCacheManager:
    def test_cache_singleton(self):
        """get_cache_manager() returns same instance."""
        from core.router.cache_manager import get_cache_manager, CacheManager
        a = get_cache_manager()
        b = get_cache_manager()
        assert a is b
        assert isinstance(a, CacheManager)

    def test_get_miss(self):
        """Cache miss returns None."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager()
        result = cm.get("totally unique query xyz 12345")
        assert result is None

    def test_set_and_get(self):
        """Store and retrieve a response."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager()
        cm.set("What is the capital of France?", "Paris", model="test")
        result = cm.get("What is the capital of France?", model="test")
        assert result == "Paris"

    def test_set_normalizes_whitespace(self):
        """Cache key is normalized (lowercase, stripped)."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager()
        cm.set("  Hello World  ", "response", model="test")
        result = cm.get("hello world", model="test")
        assert result == "response"

    def test_expiry(self):
        """Expired entries are not returned."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager(ttl_s=0.01)  # 10ms TTL
        cm.set("query_expire_test", "cached response", model="test", ttl_s=0.01)
        time.sleep(0.05)
        result = cm.get("query_expire_test", model="test")
        assert result is None

    def test_invalidate(self):
        """Invalidate removes specific entry."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager()
        cm.set("test_invalidate_query", "hello", model="test")
        removed = cm.invalidate("test_invalidate_query", model="test")
        assert removed is True
        assert cm.get("test_invalidate_query", model="test") is None

    def test_invalidate_missing(self):
        """Invalidate returns False for missing entry."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager()
        result = cm.invalidate("nonexistent query xyz", model="test")
        assert result is False

    def test_clear(self):
        """clear() removes all entries."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager()
        cm.set("q1_clear_test", "r1", model="test")
        cm.set("q2_clear_test", "r2", model="test")
        count = cm.clear()
        assert count >= 2  # at least the 2 we added
        assert cm.get("q1_clear_test", model="test") is None

    def test_purge_expired(self):
        """purge_expired removes only expired entries."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager()
        cm.set("fresh_purge_test", "fresh", model="test", ttl_s=3600)
        cm.set("expired_purge_test", "expired", model="test", ttl_s=0.001)
        time.sleep(0.01)
        removed = cm.purge_expired()
        # "fresh" should still be available
        assert cm.get("fresh_purge_test", model="test") == "fresh"

    def test_stats(self):
        """stats() returns dict with required fields."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager()
        s = cm.stats()
        assert "size" in s
        assert "hits" in s
        assert "misses" in s
        assert "hit_rate" in s

    def test_max_entries_eviction(self):
        """Cache evicts oldest entries when max_entries is exceeded."""
        from core.router.cache_manager import CacheManager
        cm = CacheManager(max_entries=5)
        for i in range(10):
            cm.set(f"query_evict_{i}", f"response_{i}", model="test")
        assert len(cm._cache) <= 5

    def test_entry_is_expired(self):
        """CacheEntry.is_expired() works correctly."""
        from core.router.cache_manager import CacheEntry
        entry = CacheEntry(
            query_hash="abc",
            query="test",
            response="response",
            model="test",
            created_at=time.time() - 7200,
            ttl_s=3600,
        )
        assert entry.is_expired()

        fresh = CacheEntry(
            query_hash="def",
            query="fresh",
            response="response",
            model="test",
            created_at=time.time(),
            ttl_s=3600,
        )
        assert not fresh.is_expired()


# ── LocalRouter ───────────────────────────────────────────────────────────


class TestLocalRouter:
    def test_router_singleton(self):
        """get_local_router() returns same instance."""
        from core.router.local_router import get_local_router, LocalRouter
        a = get_local_router()
        b = get_local_router()
        assert a is b
        assert isinstance(a, LocalRouter)

    @pytest.mark.asyncio
    async def test_route_cache_hit(self):
        """Cache hit returns immediately without calling APIs."""
        from core.router.local_router import LocalRouter, RouteSource
        router = LocalRouter()

        # Pre-populate cache (model="" matches the route() lookup key)
        router._cache.set("cached question", "cached answer", model="")

        messages = [{"role": "user", "content": "cached question"}]
        result = await router.route(messages, prefer_cache=True)

        assert result.source == RouteSource.CACHE
        assert result.content == "cached answer"
        assert result.cached is True

    @pytest.mark.asyncio
    async def test_route_kimi_success(self):
        """Successful Kimi call returns KIMI source."""
        from core.router.local_router import LocalRouter, RouteSource
        router = LocalRouter()
        router._cache._cache.clear()  # empty cache

        messages = [{"role": "user", "content": "unique_test_question_kimi_abc123"}]

        with patch.object(router, "_call_openrouter", new_callable=AsyncMock,
                          return_value="Kimi response") as mock_kimi:
            result = await router.route(messages, prefer_cache=False)

        assert result.source == RouteSource.KIMI
        assert result.content == "Kimi response"
        mock_kimi.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_falls_back_to_claude(self):
        """Falls back to Claude when Kimi fails."""
        from core.router.local_router import LocalRouter, RouteSource
        router = LocalRouter()
        router._cache._cache.clear()

        messages = [{"role": "user", "content": "test_claude_fallback_xyz"}]

        async def kimi_fail(*a, **kw):
            if kw.get("model", "").startswith("moonshot"):
                raise RuntimeError("Kimi unavailable")
            return "Claude response"

        with patch.object(router, "_call_openrouter", side_effect=kimi_fail):
            result = await router.route(messages, prefer_cache=False)

        assert result.source == RouteSource.CLAUDE
        assert result.content == "Claude response"

    @pytest.mark.asyncio
    async def test_route_all_fail_returns_error(self):
        """When all routes fail, returns ERROR source."""
        from core.router.local_router import LocalRouter, RouteSource
        router = LocalRouter()
        router._cache._cache.clear()

        messages = [{"role": "user", "content": "test_all_fail_xyz_unique"}]

        with patch.object(router, "_call_openrouter", side_effect=RuntimeError("all fail")):
            with patch.object(router, "_call_ollama", side_effect=RuntimeError("ollama fail")):
                result = await router.route(messages, prefer_cache=False)

        assert result.source == RouteSource.ERROR
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_route_caches_response(self):
        """Successful route stores response in cache."""
        from core.router.local_router import LocalRouter, RouteSource
        router = LocalRouter()
        router._cache._cache.clear()

        messages = [{"role": "user", "content": "test_cache_store_unique_xyz"}]

        with patch.object(router, "_call_openrouter", new_callable=AsyncMock,
                          return_value="stored response"):
            await router.route(messages, prefer_cache=False)

        # Should now be in cache (route() stores with model="kimi")
        cached = router._cache.get("test_cache_store_unique_xyz", model="kimi")
        assert cached == "stored response"

    def test_router_stats(self):
        """stats() returns dict with required fields."""
        from core.router.local_router import LocalRouter
        router = LocalRouter()
        s = router.stats()
        assert "routes" in s
        assert "total_calls" in s
        assert "cache_hit_rate" in s
