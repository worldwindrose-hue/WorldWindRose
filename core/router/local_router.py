"""
ROSA OS — Local Router.

Routing hierarchy for LLM calls:
  1. Cache hit → return immediately (0 tokens)
  2. Kimi K2.5 (OpenRouter) — primary cloud model
  3. Claude (OpenRouter) — fallback if Kimi fails
  4. Ollama (local) — offline fallback
  5. Cache stale read — return stale entry with warning

All routing decisions are logged for analytics.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger("rosa.router.local")


class RouteSource(str, Enum):
    CACHE = "cache"
    KIMI = "kimi"
    CLAUDE = "claude"
    OLLAMA = "ollama"
    STALE_CACHE = "stale_cache"
    ERROR = "error"


@dataclass
class RoutedResponse:
    content: str
    source: RouteSource
    model: str
    latency_ms: float
    cached: bool = False
    tokens_used: int = 0
    error: Optional[str] = None


class LocalRouter:
    """
    Routes LLM requests through the availability hierarchy.
    Falls back gracefully without raising exceptions.
    """

    def __init__(self):
        from core.router.cache_manager import get_cache_manager
        self._cache = get_cache_manager()
        self._stats: dict[str, int] = {s.value: 0 for s in RouteSource}

    async def route(
        self,
        messages: list[dict],
        *,
        session_id: str = "",
        prefer_cache: bool = True,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> RoutedResponse:
        """Route a chat completion request through the hierarchy."""
        t0 = time.monotonic()

        # Build cache key from last user message
        user_msg = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "",
        )

        # 1. Cache lookup
        if prefer_cache and user_msg:
            cached = self._cache.get(user_msg)
            if cached:
                self._stats[RouteSource.CACHE.value] += 1
                return RoutedResponse(
                    content=cached,
                    source=RouteSource.CACHE,
                    model="cache",
                    latency_ms=round((time.monotonic() - t0) * 1000, 1),
                    cached=True,
                )

        # 2. Try Kimi K2.5
        try:
            response = await self._call_openrouter(
                messages, model="moonshotai/kimi-k2.5",
                temperature=temperature, max_tokens=max_tokens,
            )
            self._stats[RouteSource.KIMI.value] += 1
            if user_msg:
                self._cache.set(user_msg, response, model="kimi")
            return RoutedResponse(
                content=response,
                source=RouteSource.KIMI,
                model="moonshotai/kimi-k2.5",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
            )
        except Exception as exc:
            logger.warning("Kimi failed, trying Claude: %s", exc)

        # 3. Try Claude (OpenRouter)
        try:
            response = await self._call_openrouter(
                messages, model="anthropic/claude-3-5-haiku",
                temperature=temperature, max_tokens=max_tokens,
            )
            self._stats[RouteSource.CLAUDE.value] += 1
            if user_msg:
                self._cache.set(user_msg, response, model="claude")
            return RoutedResponse(
                content=response,
                source=RouteSource.CLAUDE,
                model="anthropic/claude-3-5-haiku",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
            )
        except Exception as exc:
            logger.warning("Claude failed, trying Ollama: %s", exc)

        # 4. Try Ollama local
        try:
            response = await self._call_ollama(messages)
            self._stats[RouteSource.OLLAMA.value] += 1
            return RoutedResponse(
                content=response,
                source=RouteSource.OLLAMA,
                model="ollama/local",
                latency_ms=round((time.monotonic() - t0) * 1000, 1),
            )
        except Exception as exc:
            logger.warning("Ollama failed: %s", exc)

        # 5. Stale cache fallback
        if user_msg:
            stale = self._cache._cache.get(self._cache._hash(user_msg))
            if stale:
                self._stats[RouteSource.STALE_CACHE.value] += 1
                return RoutedResponse(
                    content=f"[Устаревший ответ] {stale.response}",
                    source=RouteSource.STALE_CACHE,
                    model="cache_stale",
                    latency_ms=round((time.monotonic() - t0) * 1000, 1),
                    cached=True,
                )

        # 6. Total failure
        self._stats[RouteSource.ERROR.value] += 1
        return RoutedResponse(
            content="Все маршруты недоступны. Проверьте интернет-соединение и API ключи.",
            source=RouteSource.ERROR,
            model="none",
            latency_ms=round((time.monotonic() - t0) * 1000, 1),
            error="All routes failed",
        )

    async def _call_openrouter(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        from core.config import get_settings
        import openai

        settings = get_settings()
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")

        client = openai.AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    async def _call_ollama(self, messages: list[dict]) -> str:
        try:
            import ollama
        except ImportError:
            raise RuntimeError("ollama not installed")

        # Convert to Ollama format
        prompt = "\n".join(
            f"{m['role'].capitalize()}: {m['content']}" for m in messages
        )
        # Pick best available local model: prefer rosa:latest, then llama3.2, etc.
        preferred = ["rosa:latest", "llama3.2", "qwen2.5:3b", "qwen2.5:latest"]
        try:
            available = [m["name"] for m in (await ollama.AsyncClient().list()).get("models", [])]
        except Exception:
            available = []
        model = next((m for m in preferred if m in available), None) or (available[0] if available else "llama3.2")
        logger.info("Ollama routing to model: %s (available: %s)", model, available)
        response = await ollama.AsyncClient().generate(
            model=model,
            prompt=prompt,
        )
        return response.get("response", "")

    def stats(self) -> dict:
        total = sum(self._stats.values())
        return {
            "routes": self._stats,
            "total_calls": total,
            "cache_hit_rate": round(
                (self._stats.get("cache", 0) / max(total, 1)) * 100, 1
            ),
        }


_local_router: Optional[LocalRouter] = None


def get_local_router() -> LocalRouter:
    global _local_router
    if _local_router is None:
        _local_router = LocalRouter()
    return _local_router
