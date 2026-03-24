"""
ROSA OS — Active Inference (Free Energy Principle, simplified).

Implements a minimal version of Friston's Free Energy Principle:
- Rosa maintains a generative model (beliefs) about user needs
- Each interaction updates beliefs to minimize "surprise"
- Actions are chosen to minimize expected free energy

Simplified: tracks topic probability distributions and updates
them via Bayesian-style inference on each conversation turn.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger("rosa.prediction.active_inference")

# Vocabulary of observable topics
_DEFAULT_TOPICS = [
    "code", "math", "writing", "research", "memory",
    "schedule", "analysis", "creative", "personal", "other",
]


class BeliefState:
    """
    Maintains a probability distribution over topics (beliefs).
    Updated via approximate Bayesian inference.
    """

    def __init__(self, topics: list[str] | None = None) -> None:
        self._topics = topics or _DEFAULT_TOPICS
        n = len(self._topics)
        # Start with uniform prior
        self._beliefs: dict[str, float] = {t: 1.0 / n for t in self._topics}
        self._observations: int = 0

    def update(self, observed_topic: str, strength: float = 1.0) -> None:
        """
        Update beliefs given an observed topic.
        Uses simple likelihood weighting (approximates Bayesian update).

        P(topic | obs) ∝ P(obs | topic) * P(topic)
        where P(obs | topic) = (1 + strength) if topic matches, 1 otherwise.
        """
        likelihood: dict[str, float] = {}
        for t in self._topics:
            if t == observed_topic:
                likelihood[t] = self._beliefs[t] * (1.0 + strength)
            else:
                likelihood[t] = self._beliefs[t] * (1.0 - strength * 0.1)

        # Normalize
        total = sum(likelihood.values())
        if total > 1e-9:
            self._beliefs = {t: v / total for t, v in likelihood.items()}
        self._observations += 1

    def surprise(self, observed_topic: str) -> float:
        """
        Compute surprise (negative log likelihood) for observing this topic.
        High surprise = unexpected observation.
        Returns float in [0, ∞).
        """
        p = self._beliefs.get(observed_topic, 1e-9)
        return -math.log(max(p, 1e-9))

    def free_energy(self) -> float:
        """
        Compute variational free energy ≈ entropy of belief distribution.
        Lower free energy = more confident, better model.
        H(beliefs) = -Σ p * log(p)
        """
        return -sum(
            p * math.log(max(p, 1e-9))
            for p in self._beliefs.values()
        )

    def top_beliefs(self, n: int = 3) -> list[tuple[str, float]]:
        """Return top N topics by belief probability."""
        return sorted(self._beliefs.items(), key=lambda x: -x[1])[:n]

    def most_likely_topic(self) -> str:
        """Return the topic with highest belief probability."""
        return max(self._beliefs, key=lambda t: self._beliefs[t])

    def expected_action(self) -> dict[str, Any]:
        """
        Choose an action to minimize expected free energy.
        Action = proactively ask about/prepare for the most likely topic.
        """
        top = self.top_beliefs(3)
        fe = self.free_energy()
        certainty = 1.0 - (fe / math.log(len(self._topics)))  # 0=max uncertainty, 1=certain

        return {
            "recommended_topic": top[0][0] if top else "other",
            "confidence": round(top[0][1], 4) if top else 0.0,
            "free_energy": round(fe, 4),
            "certainty": round(max(0.0, certainty), 4),
            "top_beliefs": [(t, round(p, 4)) for t, p in top],
        }

    def state_dict(self) -> dict[str, Any]:
        return {
            "beliefs": {t: round(p, 6) for t, p in self._beliefs.items()},
            "observations": self._observations,
            "free_energy": round(self.free_energy(), 4),
        }


def _classify_topic(message: str) -> str:
    """Simple keyword-based topic classifier."""
    msg = message.lower()
    if any(w in msg for w in ["код", "code", "python", "function", "error", "debug", "ошибка"]):
        return "code"
    if any(w in msg for w in ["math", "calculate", "solve", "число", "задача", "формула"]):
        return "math"
    if any(w in msg for w in ["write", "написать", "текст", "статья", "пост", "email"]):
        return "writing"
    if any(w in msg for w in ["найди", "research", "найти", "поиск", "изучи"]):
        return "research"
    if any(w in msg for w in ["remember", "запомни", "memory", "помнишь", "история"]):
        return "memory"
    if any(w in msg for w in ["schedule", "расписание", "встреча", "напомни", "завтра"]):
        return "schedule"
    if any(w in msg for w in ["анализ", "analyze", "данные", "data", "статистика"]):
        return "analysis"
    if any(w in msg for w in ["idea", "идея", "creative", "придумай", "креатив"]):
        return "creative"
    return "other"


# Module-level singleton
_belief_state: BeliefState | None = None


def get_belief_state() -> BeliefState:
    global _belief_state
    if _belief_state is None:
        _belief_state = BeliefState()
    return _belief_state


def observe(message: str) -> dict[str, Any]:
    """
    Process a user message through active inference.
    Updates beliefs and returns action recommendation.
    """
    bs = get_belief_state()
    topic = _classify_topic(message)
    surprise = bs.surprise(topic)
    bs.update(topic)
    action = bs.expected_action()

    return {
        "observed_topic": topic,
        "surprise": round(surprise, 4),
        "action": action,
    }


def get_state() -> dict[str, Any]:
    """Return current belief state summary."""
    return get_belief_state().state_dict()
