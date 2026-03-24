"""
ROSA OS — Metacognitive Evaluator.
After each response, Kimi K2.5 evaluates its own answer quality.
Runs asynchronously (fire-and-forget) — zero latency for the user.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("rosa.metacognition")

_EVAL_PROMPT = """\
You are Rosa performing a metacognitive self-evaluation of your own answer.
Rate the quality of YOUR response on a scale of 1 to 10 across 4 criteria.
Return ONLY valid JSON — no markdown, no extra text:
{{
  "completeness": <1-10>,
  "accuracy": <1-10>,
  "helpfulness": <1-10>,
  "overall": <1-10>,
  "weak_points": ["...", "..."],
  "improvement_hint": "..."
}}

Criteria:
- completeness: Did the answer fully address the question?
- accuracy: Is the information factually correct?
- helpfulness: Will this actually help the user?
- overall: Holistic quality score.
- weak_points: List up to 3 specific weaknesses (Russian or English).
- improvement_hint: One concrete suggestion for a better answer.

User question: {message}

Your response: {response}"""


async def evaluate_response(
    message: str,
    response: str,
    session_id: str,
) -> None:
    """
    Fire-and-forget: evaluate response quality with Kimi K2.5,
    save result to DB. Errors are logged but never raised.
    """
    try:
        from core.config import get_settings
        import httpx

        settings = get_settings()
        if not settings.openrouter_api_key:
            return

        prompt = _EVAL_PROMPT.format(
            message=message[:1000],
            response=response[:2000],
        )

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.cloud_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 512,
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        scores = json.loads(raw)

        from core.memory.store import get_store
        store = await get_store()
        await store.save_quality(
            session_id=session_id,
            message=message,
            response=response,
            completeness=float(scores.get("completeness", 5)),
            accuracy=float(scores.get("accuracy", 5)),
            helpfulness=float(scores.get("helpfulness", 5)),
            overall=float(scores.get("overall", 5)),
            weak_points=json.dumps(scores.get("weak_points", []), ensure_ascii=False),
            improvement_hint=scores.get("improvement_hint"),
        )
        logger.debug(
            "Quality saved: session=%s overall=%.1f",
            session_id,
            scores.get("overall", 5),
        )

        # Record habit event for pattern analysis
        try:
            await store.record_habit_event(
                task_type="chat",
                model_used=settings.cloud_model,
                session_id=session_id,
            )
        except Exception:
            pass

    except Exception as exc:
        logger.debug("Metacognition eval failed (non-critical): %s", exc)
