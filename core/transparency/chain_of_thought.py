"""
ROSA OS — Chain of Thought Visualizer.

Captures and stores Rosa's reasoning steps for transparency.
Each response can have an associated CoT trace visible in the UI.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.transparency.cot")

_COT_LOG = Path("memory/cot_traces.jsonl")
_MAX_TRACES = 200  # keep last N traces in memory


@dataclass
class ThoughtStep:
    step: int
    label: str   # e.g. "Понимание вопроса", "Поиск информации", "Формулировка ответа"
    content: str
    duration_ms: float = 0.0


@dataclass
class CoTTrace:
    trace_id: str
    session_id: str
    question: str
    steps: list[ThoughtStep]
    final_answer: str
    total_ms: float
    timestamp: str

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CoTTrace":
        steps = [ThoughtStep(**s) for s in d.pop("steps", [])]
        return cls(steps=steps, **d)


class ChainOfThoughtVisualizer:
    """
    Extracts and stores reasoning steps from LLM responses.

    Looks for <think>...</think> tags (used by Kimi K2.5),
    or falls back to heuristic step extraction.
    """

    def __init__(self):
        self._traces: list[CoTTrace] = []

    def extract_from_response(
        self,
        question: str,
        raw_response: str,
        session_id: str = "",
        trace_id: str = "",
        total_ms: float = 0.0,
    ) -> CoTTrace:
        """Parse a raw LLM response for reasoning steps."""
        import uuid
        tid = trace_id or str(uuid.uuid4())[:8]

        # Try to extract <think>...</think> blocks (Kimi K2.5 format)
        steps: list[ThoughtStep] = []
        final_answer = raw_response

        think_match = re.search(r"<think>(.*?)</think>", raw_response, re.DOTALL)
        if think_match:
            think_content = think_match.group(1).strip()
            final_answer = raw_response.replace(think_match.group(0), "").strip()

            # Split think block into numbered steps or paragraphs
            paragraphs = [p.strip() for p in think_content.split("\n\n") if p.strip()]
            labels = [
                "Анализ вопроса", "Поиск контекста", "Рассуждение",
                "Проверка", "Формулировка"
            ]
            for i, para in enumerate(paragraphs[:5]):
                steps.append(ThoughtStep(
                    step=i + 1,
                    label=labels[i] if i < len(labels) else f"Шаг {i+1}",
                    content=para[:500],
                ))
        else:
            # Heuristic: split long response into implied steps
            steps = self._heuristic_steps(question, raw_response)

        trace = CoTTrace(
            trace_id=tid,
            session_id=session_id,
            question=question[:300],
            steps=steps,
            final_answer=final_answer[:2000],
            total_ms=total_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._store_trace(trace)
        return trace

    def _heuristic_steps(self, question: str, response: str) -> list[ThoughtStep]:
        """Generate implied steps for responses without explicit CoT."""
        steps = [
            ThoughtStep(step=1, label="Анализ вопроса", content=f"Вопрос: {question[:200]}"),
        ]
        if len(response) > 300:
            steps.append(ThoughtStep(
                step=2,
                label="Формулировка ответа",
                content=response[:300] + "...",
            ))
        return steps

    def _store_trace(self, trace: CoTTrace) -> None:
        """Append trace to in-memory list and persist to JSONL."""
        self._traces.append(trace)
        if len(self._traces) > _MAX_TRACES:
            self._traces = self._traces[-_MAX_TRACES:]
        try:
            _COT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with _COT_LOG.open("a") as f:
                f.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_recent_traces(self, limit: int = 20) -> list[CoTTrace]:
        return self._traces[-limit:]

    def get_trace(self, trace_id: str) -> Optional[CoTTrace]:
        return next((t for t in self._traces if t.trace_id == trace_id), None)


_cot: Optional[ChainOfThoughtVisualizer] = None


def get_cot_visualizer() -> ChainOfThoughtVisualizer:
    global _cot
    if _cot is None:
        _cot = ChainOfThoughtVisualizer()
    return _cot
