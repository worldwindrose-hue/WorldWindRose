"""
ROSA OS — Dynamic Capability Map.

Tracks Rosa's skill levels across 6 categories.
Auto-updates after each task: success → +0.1, failure → -0.05.
Persists to memory/capabilities.json.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.metacognition.capabilities")

_CAP_FILE = Path("memory/capabilities.json")

_DEFAULT_CAPABILITIES = {
    # coding
    "python": {"category": "coding", "level": 3.0, "success_rate": 0.8},
    "javascript": {"category": "coding", "level": 2.5, "success_rate": 0.7},
    "sql": {"category": "coding", "level": 2.5, "success_rate": 0.75},
    "bash": {"category": "coding", "level": 2.5, "success_rate": 0.7},
    # research
    "web_search": {"category": "research", "level": 3.5, "success_rate": 0.85},
    "academic": {"category": "research", "level": 2.5, "success_rate": 0.7},
    # memory
    "recall": {"category": "memory", "level": 3.0, "success_rate": 0.8},
    "graph": {"category": "memory", "level": 2.5, "success_rate": 0.7},
    "context": {"category": "memory", "level": 3.0, "success_rate": 0.8},
    # reasoning
    "math": {"category": "reasoning", "level": 2.5, "success_rate": 0.65},
    "logic": {"category": "reasoning", "level": 3.0, "success_rate": 0.75},
    "causal": {"category": "reasoning", "level": 2.5, "success_rate": 0.7},
    # creation
    "text_writing": {"category": "creation", "level": 3.5, "success_rate": 0.85},
    "code_generation": {"category": "creation", "level": 3.0, "success_rate": 0.8},
    "planning": {"category": "creation", "level": 3.0, "success_rate": 0.78},
    # tools
    "web_tools": {"category": "tools", "level": 3.0, "success_rate": 0.8},
    "file_system": {"category": "tools", "level": 2.5, "success_rate": 0.75},
    "mac_control": {"category": "tools", "level": 2.0, "success_rate": 0.65},
    # general fallback
    "coding": {"category": "coding", "level": 3.0, "success_rate": 0.8},
    "research": {"category": "research", "level": 3.0, "success_rate": 0.8},
    "memory": {"category": "memory", "level": 3.0, "success_rate": 0.8},
    "reasoning": {"category": "reasoning", "level": 3.0, "success_rate": 0.75},
    "creation": {"category": "creation", "level": 3.0, "success_rate": 0.8},
    "tools": {"category": "tools", "level": 2.5, "success_rate": 0.75},
}


@dataclass
class Capability:
    name: str
    category: str
    level: float       # 1.0 – 5.0
    success_rate: float  # 0.0 – 1.0
    total_uses: int = 0
    successes: int = 0
    last_tested: str = ""
    examples: list[str] = None

    def __post_init__(self):
        if self.examples is None:
            self.examples = []
        if not self.last_tested:
            self.last_tested = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class CapabilityMap:
    """Persistent capability tracker."""

    def __init__(self):
        self._caps: dict[str, Capability] = {}
        self.load()

    def load(self) -> dict[str, Capability]:
        """Load from disk or seed defaults."""
        if _CAP_FILE.exists():
            try:
                raw = json.loads(_CAP_FILE.read_text())
                self._caps = {}
                for name, data in raw.items():
                    data.setdefault("name", name)
                    data.setdefault("total_uses", 0)
                    data.setdefault("successes", 0)
                    data.setdefault("examples", [])
                    data.setdefault("last_tested", "")
                    self._caps[name] = Capability(**data)
                return self._caps
            except Exception as exc:
                logger.warning("Failed to load capability map: %s", exc)

        # Seed defaults
        self._caps = {}
        for name, data in _DEFAULT_CAPABILITIES.items():
            self._caps[name] = Capability(
                name=name,
                category=data["category"],
                level=data["level"],
                success_rate=data["success_rate"],
            )
        self.save()
        return self._caps

    def save(self) -> None:
        try:
            _CAP_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {name: cap.to_dict() for name, cap in self._caps.items()}
            _CAP_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        except Exception as exc:
            logger.warning("Failed to save capability map: %s", exc)

    def get(self, name: str) -> Optional[Capability]:
        return self._caps.get(name)

    def record_success(self, capability_name: str) -> None:
        cap = self._ensure(capability_name)
        cap.total_uses += 1
        cap.successes += 1
        cap.level = min(5.0, cap.level + 0.1)
        cap.success_rate = cap.successes / max(cap.total_uses, 1)
        cap.last_tested = datetime.now(timezone.utc).isoformat()
        self.save()

    def record_failure(self, capability_name: str) -> None:
        cap = self._ensure(capability_name)
        cap.total_uses += 1
        cap.level = max(1.0, cap.level - 0.05)
        cap.success_rate = cap.successes / max(cap.total_uses, 1)
        cap.last_tested = datetime.now(timezone.utc).isoformat()
        self.save()

    def get_gaps(self) -> list[Capability]:
        """Return capabilities with level < 2.5 — areas to improve."""
        return sorted(
            [c for c in self._caps.values() if c.level < 2.5],
            key=lambda c: c.level,
        )

    def to_dict(self) -> dict:
        return {name: cap.to_dict() for name, cap in self._caps.items()}

    def summary(self) -> dict:
        """Category-level summary."""
        by_cat: dict[str, list[float]] = {}
        for cap in self._caps.values():
            by_cat.setdefault(cap.category, []).append(cap.level)
        return {
            cat: round(sum(levels) / len(levels), 2)
            for cat, levels in by_cat.items()
        }

    def _ensure(self, name: str) -> Capability:
        if name not in self._caps:
            self._caps[name] = Capability(
                name=name, category="general", level=2.5, success_rate=0.7
            )
        return self._caps[name]


_map_instance: Optional[CapabilityMap] = None


def get_capability_map() -> CapabilityMap:
    global _map_instance
    if _map_instance is None:
        _map_instance = CapabilityMap()
    return _map_instance
