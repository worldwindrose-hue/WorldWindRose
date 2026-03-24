"""
ROSA OS — Token Economy Optimizer (Phase 9).

Strategies:
1. Response cache (cosine similarity threshold)
2. Smart cost-based routing
3. Context compression when history > 8000 tokens
4. Token usage tracking per model

All data stored in memory/token_usage.json.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.economy")

_USAGE_FILE = Path("memory/token_usage.json")
_SIMILARITY_THRESHOLD = 0.92
_CONTEXT_COMPRESS_THRESHOLD = 8000  # tokens

# Cost per 1M tokens (input/output) in USD
_MODEL_COSTS: dict[str, dict[str, float]] = {
    "moonshotai/kimi-k2.5":      {"input": 0.60, "output": 2.50},
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "google/gemini-flash-1.5":   {"input": 0.075, "output": 0.30},
    "openai/gpt-4o":             {"input": 5.00, "output": 15.00},
    "perplexity/sonar-pro":      {"input": 3.00, "output": 15.00},
    "llama3.2":                  {"input": 0.00, "output": 0.00},   # local
}


def _load_usage() -> dict[str, Any]:
    if _USAGE_FILE.exists():
        try:
            return json.loads(_USAGE_FILE.read_text())
        except Exception:
            pass
    return {"daily": {}, "monthly": {}, "total": {}, "cache_hits": 0, "cache_misses": 0}


def _save_usage(data: dict) -> None:
    _USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _USAGE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def record_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    """Record token usage for a model."""
    usage = _load_usage()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    for period, key in [(usage["daily"], today), (usage["monthly"], month), (usage["total"], "all")]:
        if key not in period:
            period[key] = {}
        if model not in period[key]:
            period[key][model] = {"input": 0, "output": 0, "cost_usd": 0.0}
        period[key][model]["input"] += input_tokens
        period[key][model]["output"] += output_tokens
        costs = _MODEL_COSTS.get(model, {"input": 1.0, "output": 3.0})
        cost = (input_tokens / 1_000_000) * costs["input"] + (output_tokens / 1_000_000) * costs["output"]
        period[key][model]["cost_usd"] = round(period[key][model]["cost_usd"] + cost, 6)

    _save_usage(usage)


def get_usage_stats() -> dict[str, Any]:
    """Return usage statistics."""
    usage = _load_usage()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    daily = usage["daily"].get(today, {})
    monthly = usage["monthly"].get(month, {})
    total = usage["total"].get("all", {})

    def _sum_cost(d: dict) -> float:
        return round(sum(v.get("cost_usd", 0) for v in d.values()), 4)

    return {
        "today_cost_usd": _sum_cost(daily),
        "month_cost_usd": _sum_cost(monthly),
        "total_cost_usd": _sum_cost(total),
        "cache_hits": usage.get("cache_hits", 0),
        "cache_misses": usage.get("cache_misses", 0),
        "by_model": {
            "today": daily,
            "this_month": monthly,
        },
    }


def estimate_tokens(text: str) -> int:
    """Rough token count estimate (4 chars ≈ 1 token)."""
    return max(1, len(text) // 4)


async def should_use_cache(query: str, cache: list[dict]) -> dict | None:
    """
    Check if a cached response is similar enough to reuse.
    Returns cached entry or None.
    """
    if not cache:
        return None
    q_lower = query.lower()
    for entry in cache:
        cached_q = entry.get("query", "").lower()
        # Simple word overlap similarity
        q_words = set(q_lower.split())
        c_words = set(cached_q.split())
        if not q_words or not c_words:
            continue
        overlap = len(q_words & c_words) / max(len(q_words), len(c_words))
        if overlap >= _SIMILARITY_THRESHOLD:
            return entry
    return None


async def compress_context(messages: list[dict]) -> list[dict]:
    """
    If context is too long, summarize the older portion.
    Returns compressed messages list.
    """
    total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    if total_tokens <= _CONTEXT_COMPRESS_THRESHOLD:
        return messages

    # Keep last 10 messages, summarize the rest
    to_keep = messages[-10:]
    to_compress = messages[:-10]

    if not to_compress:
        return messages

    try:
        from openai import AsyncOpenAI
        from core.config import get_settings
        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
        conversation = "\n".join(f"{m['role']}: {m['content'][:200]}" for m in to_compress)
        resp = await client.chat.completions.create(
            model="google/gemini-flash-1.5",  # cheapest
            messages=[{"role": "user", "content": f"Summarize this conversation briefly:\n{conversation}"}],
            max_tokens=200,
        )
        summary = resp.choices[0].message.content or ""
        compressed = [{"role": "system", "content": f"[Context summary]: {summary}"}] + to_keep
        logger.info("Context compressed: %d → %d messages", len(messages), len(compressed))
        return compressed
    except Exception as exc:
        logger.debug("Context compression failed: %s", exc)
        return messages


def route_by_cost(task_type: str, economy_mode: bool = False) -> str:
    """Return cheapest appropriate model for task type."""
    if economy_mode:
        return "google/gemini-flash-1.5"

    routing = {
        "CODE_GENERATION": "anthropic/claude-3.5-sonnet",
        "VISION_ANALYSIS": "google/gemini-flash-1.5",
        "WEB_SEARCH": "perplexity/sonar-pro",
        "FAST_RESPONSE": "google/gemini-flash-1.5",
        "SIMPLE_CHAT": "google/gemini-flash-1.5",
        "PRIVATE_FILE": "llama3.2",
    }
    return routing.get(task_type, "moonshotai/kimi-k2.5")
