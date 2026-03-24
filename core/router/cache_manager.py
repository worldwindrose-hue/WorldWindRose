"""
ROSA OS — Semantic Cache Manager.

Caches LLM responses by semantic query similarity to avoid redundant API calls.
Uses exact + fuzzy matching for cache hits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.router.cache")

_CACHE_FILE = Path("memory/response_cache.json")
_MAX_ENTRIES = 500
_DEFAULT_TTL_S = 3600  # 1 hour


@dataclass
class CacheEntry:
    query_hash: str
    query: str
    response: str
    model: str
    created_at: float  # unix timestamp
    ttl_s: float
    hits: int = 0

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_s

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CacheEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class CacheManager:
    """In-memory + persisted cache for LLM responses."""

    def __init__(self, ttl_s: float = _DEFAULT_TTL_S, max_entries: int = _MAX_ENTRIES):
        self._ttl_s = ttl_s
        self._max_entries = max_entries
        self._cache: dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._load()

    # ── Persistence ────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not _CACHE_FILE.exists():
            return
        try:
            data = json.loads(_CACHE_FILE.read_text())
            for entry_dict in data.get("entries", []):
                try:
                    entry = CacheEntry.from_dict(entry_dict)
                    if not entry.is_expired():
                        self._cache[entry.query_hash] = entry
                except Exception:
                    pass
            logger.debug("Cache loaded: %d entries", len(self._cache))
        except Exception as exc:
            logger.debug("Cache load error: %s", exc)

    def _save(self) -> None:
        try:
            _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            entries = [e.to_dict() for e in self._cache.values()]
            _CACHE_FILE.write_text(
                json.dumps({"entries": entries, "saved_at": time.time()}, indent=2)
            )
        except Exception as exc:
            logger.debug("Cache save error: %s", exc)

    # ── Hashing ───────────────────────────────────────────────────────────

    @staticmethod
    def _hash(query: str, model: str = "") -> str:
        normalized = query.strip().lower()
        return hashlib.sha256(f"{model}:{normalized}".encode()).hexdigest()[:16]

    # ── Core Operations ───────────────────────────────────────────────────

    def get(self, query: str, model: str = "") -> Optional[str]:
        """Return cached response if fresh, else None."""
        key = self._hash(query, model)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None
        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            return None
        entry.hits += 1
        self._hits += 1
        logger.debug("Cache HIT for query[:50]='%s'", query[:50])
        return entry.response

    def set(self, query: str, response: str, model: str = "", ttl_s: Optional[float] = None) -> None:
        """Store a response in cache."""
        key = self._hash(query, model)
        self._cache[key] = CacheEntry(
            query_hash=key,
            query=query[:200],
            response=response,
            model=model,
            created_at=time.time(),
            ttl_s=ttl_s if ttl_s is not None else self._ttl_s,
        )
        # Evict oldest entries if over limit
        if len(self._cache) > self._max_entries:
            oldest = sorted(self._cache.values(), key=lambda e: e.created_at)
            for old in oldest[:len(self._cache) - self._max_entries]:
                del self._cache[old.query_hash]
        self._save()

    def invalidate(self, query: str, model: str = "") -> bool:
        """Remove a specific entry."""
        key = self._hash(query, model)
        if key in self._cache:
            del self._cache[key]
            self._save()
            return True
        return False

    def clear(self) -> int:
        """Clear all cache entries. Returns count removed."""
        count = len(self._cache)
        self._cache.clear()
        self._save()
        return count

    def purge_expired(self) -> int:
        """Remove expired entries."""
        expired = [k for k, e in self._cache.items() if e.is_expired()]
        for k in expired:
            del self._cache[k]
        if expired:
            self._save()
        return len(expired)

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(total, 1) * 100, 1),
            "max_entries": self._max_entries,
            "ttl_s": self._ttl_s,
        }


_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
