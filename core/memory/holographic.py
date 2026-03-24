"""
ROSA OS — Holographic Memory (HRR approximation).
Uses numpy for fast context encoding/decoding.

Holographic Reduced Representations (HRR) encode structured data
into fixed-size vectors. This is a simplified approximation using:
  - Random projection encoding (vectors → 512-dim space)
  - Circular convolution for binding (≈ HRR superposition)
  - Cosine similarity for retrieval

References: Plate (1995), Kanerva (2009)
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any

import numpy as np

logger = logging.getLogger("rosa.memory.holographic")

VECTOR_DIM = 512
_CACHE_SIZE = 100


class HolographicStore:
    """
    Stores the last _CACHE_SIZE session contexts as 512-dim vectors.
    Supports fast similarity search for related contexts.
    """

    def __init__(self, dim: int = VECTOR_DIM, cache_size: int = _CACHE_SIZE) -> None:
        self._dim = dim
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._vectors: dict[str, np.ndarray] = {}
        self._cache_size = cache_size
        # Seed RNG for reproducible random projections
        self._rng = np.random.default_rng(seed=42)
        # Projection matrix: vocab_hash → vector
        self._proj: dict[str, np.ndarray] = {}

    def _token_vector(self, token: str) -> np.ndarray:
        """Get or create a random unit vector for a token."""
        if token not in self._proj:
            v = self._rng.standard_normal(self._dim)
            v /= np.linalg.norm(v) + 1e-9
            self._proj[token] = v
        return self._proj[token]

    def encode_context(self, messages: list[str]) -> np.ndarray:
        """
        Encode a list of message strings into a 512-dim context vector.
        Uses superposition of token vectors (simplified HRR).
        """
        vec = np.zeros(self._dim)
        for msg in messages:
            tokens = msg.lower().split()[:100]  # cap at 100 tokens per message
            for token in tokens:
                vec += self._token_vector(token)
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vec /= norm
        return vec

    def decode_context(self, vector: np.ndarray, top_k: int = 5) -> str:
        """
        Find the top_k stored sessions most similar to the query vector.
        Returns a summary string.
        """
        if not self._vectors:
            return "No stored contexts."

        sims: list[tuple[float, str]] = []
        for session_id, sv in self._vectors.items():
            sim = float(np.dot(vector, sv))
            sims.append((sim, session_id))

        sims.sort(key=lambda x: -x[0])
        top = sims[:top_k]

        lines = []
        for sim, sid in top:
            meta = self._cache.get(sid, {})
            preview = meta.get("preview", "")[:80]
            lines.append(f"  [sim={sim:.2f}] {sid}: {preview}")

        return "Related contexts:\n" + "\n".join(lines) if lines else "No similar contexts found."

    def store_session(self, session_id: str, messages: list[str], meta: dict | None = None) -> None:
        """Encode and cache a session context."""
        vec = self.encode_context(messages)
        preview = " | ".join(m[:40] for m in messages[:3])

        if len(self._cache) >= self._cache_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
            self._vectors.pop(oldest, None)

        self._cache[session_id] = {"preview": preview, **(meta or {})}
        self._vectors[session_id] = vec

    def find_similar(self, query_messages: list[str], top_k: int = 5) -> list[dict]:
        """Find top_k most similar stored sessions."""
        qv = self.encode_context(query_messages)
        sims: list[tuple[float, str]] = [
            (float(np.dot(qv, sv)), sid)
            for sid, sv in self._vectors.items()
        ]
        sims.sort(key=lambda x: -x[0])
        return [
            {"session_id": sid, "similarity": sim, **self._cache.get(sid, {})}
            for sim, sid in sims[:top_k]
        ]

    def stats(self) -> dict:
        return {
            "stored_sessions": len(self._cache),
            "vector_dim": self._dim,
            "cache_capacity": self._cache_size,
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_holographic_store: HolographicStore | None = None


def get_holographic_store() -> HolographicStore:
    global _holographic_store
    if _holographic_store is None:
        _holographic_store = HolographicStore()
    return _holographic_store


# Convenience functions

def encode_context(messages: list[str]) -> np.ndarray:
    return get_holographic_store().encode_context(messages)


def decode_context(vector: np.ndarray) -> str:
    return get_holographic_store().decode_context(vector)
