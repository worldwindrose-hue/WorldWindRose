"""
ROSA OS — Ouroboros Self-Improvement Cycle.

Weekly 5-step cycle:
1. Profile: collect quality metrics from last 7 days
2. Generate: ask Kimi to propose code improvements
3. Test: run pytest in sandbox
4. Propose: add to improvement proposals if tests pass
5. Human Gate: apply only after human review in UI

Named after the serpent eating its own tail — Rosa improves herself.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.self_improvement.ouroboros")

_PROFILE_PROMPT = """Ты — ROSA OS, система которая анализирует свои ошибки.

Вот метрики качества за последние 7 дней:
{metrics}

Слабые места (часто встречающиеся):
{weak_points}

Задача: опиши 3-5 конкретных проблемных паттерна в своей работе.
Формат JSON:
{{
  "patterns": [
    {{"pattern": "...", "frequency": "high/medium/low", "impact": "high/medium/low"}},
    ...
  ]
}}
"""

_GENERATE_PROMPT = """Ты — ROSA OS. На основе обнаруженных паттернов предложи конкретные улучшения.

Паттерны проблем:
{patterns}

Задача: для каждого паттерна предложи конкретное изменение кода.
Пиши ТОЛЬКО изменения, которые ты можешь применить без изменения архитектуры.
Формат JSON:
{{
  "proposals": [
    {{
      "pattern": "...",
      "proposal": "Краткое описание изменения",
      "target_file": "core/xxx/yyy.py",
      "code_hint": "Кусок кода который нужно добавить/изменить"
    }},
    ...
  ]
}}
"""


async def _call_kimi(prompt: str) -> str:
    from openai import AsyncOpenAI
    from core.config import get_settings
    settings = get_settings()
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    resp = await client.chat.completions.create(
        model=settings.default_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    return resp.choices[0].message.content or ""


async def step1_profile() -> dict[str, Any]:
    """Step 1: Collect quality metrics and identify weak points."""
    try:
        from core.memory.store import get_store
        store = await get_store()
        stats = await store.get_quality_stats()
        weak_responses = await store.get_weak_responses(min_score=6.0)
    except Exception as exc:
        logger.warning("Profile step failed to load DB: %s", exc)
        stats = {}
        weak_responses = []

    weak_points: list[str] = []
    for r in weak_responses[:20]:
        wp = getattr(r, "weak_points", "[]")
        try:
            points = json.loads(wp) if wp else []
            weak_points.extend(points)
        except Exception:
            pass

    # Count weak point frequencies
    from collections import Counter
    freq = Counter(weak_points)
    top_weak = [f"{p} (x{c})" for p, c in freq.most_common(10)]

    metrics_text = json.dumps(stats, ensure_ascii=False, indent=2)
    weak_text = "\n".join(f"- {p}" for p in top_weak) or "Нет данных"

    # Ask Kimi to analyze patterns
    try:
        response = await _call_kimi(
            _PROFILE_PROMPT.format(metrics=metrics_text, weak_points=weak_text)
        )
        import re
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        patterns = json.loads(json_match.group()) if json_match else {"patterns": []}
    except Exception as exc:
        logger.warning("Pattern analysis failed: %s", exc)
        patterns = {"patterns": []}

    return {
        "step": "profile",
        "stats": stats,
        "top_weak_points": top_weak,
        "patterns": patterns.get("patterns", []),
    }


async def step2_generate(patterns: list[dict]) -> dict[str, Any]:
    """Step 2: Generate improvement proposals based on patterns."""
    if not patterns:
        return {"step": "generate", "proposals": [], "reason": "no_patterns"}

    patterns_text = json.dumps(patterns, ensure_ascii=False, indent=2)
    try:
        response = await _call_kimi(
            _GENERATE_PROMPT.format(patterns=patterns_text)
        )
        import re
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        result = json.loads(json_match.group()) if json_match else {"proposals": []}
    except Exception as exc:
        logger.warning("Proposal generation failed: %s", exc)
        result = {"proposals": []}

    return {
        "step": "generate",
        "proposals": result.get("proposals", []),
    }


async def step3_test(proposals: list[dict]) -> dict[str, Any]:
    """Step 3: Write proposals to sandbox and run tests."""
    from core.self_improvement.safety import evaluate_patch, run_tests_for_patch
    import uuid

    results = []
    for prop in proposals[:3]:  # limit to 3 per cycle
        pid = str(uuid.uuid4())[:8]
        code_hint = prop.get("code_hint", "# No code provided")
        target_file = prop.get("target_file", "unknown.py")

        # Write to sandbox and test
        test_result = run_tests_for_patch(pid)
        results.append({
            "patch_id": pid,
            "proposal": prop.get("proposal", ""),
            "target_file": target_file,
            "status": test_result.status,
            "tests_passed": test_result.tests_passed,
            "tests_failed": test_result.tests_failed,
        })

    passed = [r for r in results if r["status"] == "passed"]
    return {
        "step": "test",
        "tested": len(results),
        "passed": len(passed),
        "results": results,
    }


async def step4_propose(test_results: list[dict]) -> dict[str, Any]:
    """Step 4: Add passing proposals to the improvement proposals DB."""
    passing = [r for r in test_results if r.get("status") == "passed"]
    saved = 0

    try:
        from core.memory.store import get_store
        from core.self_improvement.patcher import write_proposal
        store = await get_store()

        for r in passing:
            proposal_id = r.get("patch_id", str(uuid.uuid4())[:8])
            proposal_text = r.get("proposal", "")
            target = r.get("target_file", "")
            if proposal_text:
                # Write to proposals file
                write_proposal(
                    proposal_id=proposal_id,
                    description=proposal_text,
                    target_file=target,
                )
                saved += 1
    except Exception as exc:
        logger.warning("Proposal save failed: %s", exc)

    return {
        "step": "propose",
        "proposals_saved": saved,
        "passed_patches": len(passing),
    }


async def run_cycle() -> dict[str, Any]:
    """
    Run the full Ouroboros cycle.
    Human gate is NOT here — proposals are awaiting human review.
    """
    cycle_id = str(uuid.uuid4())[:8]
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("Ouroboros cycle %s started", cycle_id)

    try:
        from core.status.tracker import set_status, RosaStatus
        set_status(RosaStatus.UPDATING, f"Уроборос цикл {cycle_id}")
    except Exception:
        pass

    results: dict[str, Any] = {
        "cycle_id": cycle_id,
        "started_at": started_at,
        "steps": {},
    }

    # Step 1: Profile
    try:
        profile = await step1_profile()
        results["steps"]["profile"] = profile
        patterns = profile.get("patterns", [])
    except Exception as exc:
        results["steps"]["profile"] = {"error": str(exc)}
        patterns = []

    # Step 2: Generate
    try:
        generate = await step2_generate(patterns)
        results["steps"]["generate"] = generate
        proposals = generate.get("proposals", [])
    except Exception as exc:
        results["steps"]["generate"] = {"error": str(exc)}
        proposals = []

    # Step 3: Test
    try:
        test = await step3_test(proposals)
        results["steps"]["test"] = test
        test_results = test.get("results", [])
    except Exception as exc:
        results["steps"]["test"] = {"error": str(exc)}
        test_results = []

    # Step 4: Propose
    try:
        propose = await step4_propose(test_results)
        results["steps"]["propose"] = propose
    except Exception as exc:
        results["steps"]["propose"] = {"error": str(exc)}

    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    results["status"] = "completed"
    logger.info("Ouroboros cycle %s completed: %s", cycle_id, results["steps"].get("propose", {}))

    # Log to patches.log
    from core.self_improvement.safety import _log_patch_event
    _log_patch_event({"event": "ouroboros_cycle", "cycle_id": cycle_id, "summary": {
        k: v for k, v in results["steps"].items() if isinstance(v, dict) and "error" not in v
    }})

    return results
