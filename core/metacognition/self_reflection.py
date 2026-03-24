"""
ROSA OS — Self-Reflection Engine.

After every Rosa response, fire-and-forget analysis:
hallucination check, completeness, gap detection.
Results logged to memory/self_reflection.log (JSONL).
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.metacognition.reflection")

_LOG_FILE = Path("memory/self_reflection.log")
_REFLECTION_PROMPT = """Оцени ответ AI-ассистента по следующим критериям. Отвечай ТОЛЬКО JSON.

Вопрос пользователя: {question}

Ответ ассистента: {response}

Верни JSON:
{{
  "score": 0.0-1.0,
  "hallucination_risk": 0.0-1.0,
  "completeness": 0.0-1.0,
  "gaps": ["список пробелов в знаниях"],
  "improvement_tasks": ["конкретные задачи для улучшения"]
}}"""


@dataclass
class ReflectionResult:
    response_id: str
    score: float
    hallucination_risk: float
    completeness: float
    gaps: list[str]
    improvement_tasks: list[str]
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


async def reflect_on_response(
    question: str,
    response: str,
    response_id: str = "",
) -> ReflectionResult:
    """Analyse a Rosa response. Never raises — always returns a result."""
    import uuid
    rid = response_id or str(uuid.uuid4())[:8]

    # Fast heuristic scoring (no API needed)
    score = _heuristic_score(question, response)
    hallucination_risk = _estimate_hallucination(response)
    completeness = min(1.0, len(response) / max(len(question) * 3, 200))
    gaps: list[str] = []
    improvement_tasks: list[str] = []

    # Try LLM deep analysis (fire-and-forget, best-effort)
    try:
        llm_result = await _llm_reflect(question, response)
        if llm_result:
            score = llm_result.get("score", score)
            hallucination_risk = llm_result.get("hallucination_risk", hallucination_risk)
            completeness = llm_result.get("completeness", completeness)
            gaps = llm_result.get("gaps", [])
            improvement_tasks = llm_result.get("improvement_tasks", [])
    except Exception as exc:
        logger.debug("LLM reflection skipped: %s", exc)

    result = ReflectionResult(
        response_id=rid,
        score=round(score, 3),
        hallucination_risk=round(hallucination_risk, 3),
        completeness=round(completeness, 3),
        gaps=gaps[:5],
        improvement_tasks=improvement_tasks[:3],
    )
    await log_reflection(result)

    # Update capability map based on score
    _update_capabilities(score, question)

    return result


def _heuristic_score(question: str, response: str) -> float:
    """Fast rule-based quality estimate."""
    if not response.strip():
        return 0.0
    length_ok = 0.3 if len(response) > 50 else 0.1
    # Check response is related to question (keyword overlap)
    q_words = set(question.lower().split())
    r_words = set(response.lower().split())
    overlap = len(q_words & r_words) / max(len(q_words), 1)
    relevance = min(0.7, overlap * 2)
    return round(length_ok + relevance, 3)


def _estimate_hallucination(response: str) -> float:
    """Estimate hallucination risk from hedging language."""
    HIGH_RISK = ["я уверен", "точно", "100%", "гарантирую", "факт"]
    LOW_RISK = ["возможно", "вероятно", "я не уверен", "не знаю", "может быть"]
    text = response.lower()
    high = sum(1 for p in HIGH_RISK if p in text)
    low = sum(1 for p in LOW_RISK if p in text)
    if high > low:
        return 0.6
    if low > high:
        return 0.2
    return 0.4


def _update_capabilities(score: float, question: str) -> None:
    """Update capability map after reflection."""
    try:
        from core.metacognition.capability_map import get_capability_map
        cap_map = get_capability_map()
        # Simple keyword-based capability detection
        q = question.lower()
        cap = "reasoning"
        if any(w in q for w in ["код", "python", "function", "class", "code"]):
            cap = "coding"
        elif any(w in q for w in ["найди", "search", "поиск", "найти"]):
            cap = "research"
        elif any(w in q for w in ["помни", "remember", "memory", "запомни"]):
            cap = "memory"
        if score >= 0.7:
            cap_map.record_success(cap)
        elif score < 0.4:
            cap_map.record_failure(cap)
    except Exception:
        pass


async def _llm_reflect(question: str, response: str) -> Optional[dict]:
    """Ask Kimi to score the response. Returns parsed JSON or None."""
    try:
        import httpx
        from core.config import get_settings
        settings = get_settings()
        if not settings.openrouter_api_key:
            return None
        prompt = _REFLECTION_PROMPT.format(
            question=question[:500],
            response=response[:1000],
        )
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json={
                    "model": "moonshotai/kimi-k2.5",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.1,
                },
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
            # Extract JSON from response
            import re
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                return json.loads(m.group())
    except Exception as exc:
        logger.debug("LLM reflection call failed: %s", exc)
    return None


async def log_reflection(result: ReflectionResult) -> None:
    """Append result to JSONL log file."""
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Failed to log reflection: %s", exc)


def load_reflections(limit: int = 100) -> list[dict]:
    """Load last N reflections from log."""
    if not _LOG_FILE.exists():
        return []
    try:
        lines = _LOG_FILE.read_text().strip().splitlines()
        results = []
        for line in lines[-limit:]:
            try:
                results.append(json.loads(line))
            except Exception:
                pass
        return results
    except Exception:
        return []


def fire_and_forget_reflect(question: str, response: str, response_id: str = "") -> None:
    """Schedule reflection without blocking the caller."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(reflect_on_response(question, response, response_id))
    except Exception:
        pass
