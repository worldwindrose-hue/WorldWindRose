"""
ROSA OS — Agent Swarm Coordinator.

Manages a swarm of specialized sub-agents that work in parallel on different aspects of a task.
Each agent has a role, prompt, and result. Results are synthesized by a coordinator.

Roles:
- researcher: web search + knowledge graph
- analyst: data analysis + reasoning
- writer: content generation
- critic: review and improve
- planner: break task into subtasks
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("rosa.agents.swarm")

# Agent role definitions
AGENT_ROLES = {
    "researcher": {
        "system": "Ты — исследователь. Твоя задача: найти и систематизировать факты по теме. Будь конкретен.",
        "max_tokens": 1024,
    },
    "analyst": {
        "system": "Ты — аналитик. Твоя задача: проанализировать данные, найти паттерны и инсайты.",
        "max_tokens": 1024,
    },
    "writer": {
        "system": "Ты — писатель. Твоя задача: создать убедительный, читаемый контент на основе данных.",
        "max_tokens": 2048,
    },
    "critic": {
        "system": "Ты — критик. Твоя задача: найти слабые места, ошибки и предложить улучшения.",
        "max_tokens": 512,
    },
    "planner": {
        "system": "Ты — планировщик. Твоя задача: разбить задачу на конкретные шаги и распределить роли.",
        "max_tokens": 512,
    },
}

_SYNTHESIS_PROMPT = """Ты — координатор роя агентов. Собери финальный ответ из результатов агентов.

Задача: {task}

Результаты агентов:
{results}

Инструкция: синтезируй лучшие части, устрани противоречия, создай единый структурированный ответ.
"""


async def _call_agent(role: str, task: str, context: str = "") -> dict[str, Any]:
    """Call a single agent with its role prompt."""
    from openai import AsyncOpenAI
    from core.config import get_settings
    settings = get_settings()

    role_config = AGENT_ROLES.get(role, AGENT_ROLES["analyst"])
    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )

    messages = [{"role": "system", "content": role_config["system"]}]
    if context:
        messages.append({"role": "user", "content": f"Контекст:\n{context}\n\nЗадача: {task}"})
    else:
        messages.append({"role": "user", "content": task})

    try:
        resp = await client.chat.completions.create(
            model=settings.default_model,
            messages=messages,
            max_tokens=role_config["max_tokens"],
        )
        content = resp.choices[0].message.content or ""
        return {"role": role, "result": content, "success": True}
    except Exception as exc:
        logger.warning("Agent %s failed: %s", role, exc)
        return {"role": role, "result": "", "success": False, "error": str(exc)}


async def run_swarm(
    task: str,
    roles: list[str] | None = None,
    context: str = "",
    synthesize: bool = True,
) -> dict[str, Any]:
    """
    Run a swarm of agents in parallel on a task.

    Args:
        task: The task description
        roles: List of agent roles to activate (default: researcher + analyst + writer)
        context: Optional background context
        synthesize: Whether to synthesize results with coordinator

    Returns:
        {"task": str, "agent_results": list, "synthesis": str, "roles_used": list}
    """
    active_roles = roles or ["researcher", "analyst", "writer"]

    # Run all agents in parallel
    agent_tasks = [_call_agent(role, task, context) for role in active_roles]
    results = await asyncio.gather(*agent_tasks)

    # Build synthesis input
    results_text = "\n\n".join(
        f"**{r['role'].upper()}:**\n{r['result']}"
        for r in results
        if r.get("success") and r.get("result")
    )

    synthesis = ""
    if synthesize and results_text:
        try:
            from openai import AsyncOpenAI
            from core.config import get_settings
            settings = get_settings()
            client = AsyncOpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            )
            synth_prompt = _SYNTHESIS_PROMPT.format(task=task, results=results_text)
            resp = await client.chat.completions.create(
                model=settings.default_model,
                messages=[{"role": "user", "content": synth_prompt}],
                max_tokens=2048,
            )
            synthesis = resp.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("Synthesis failed: %s", exc)
            # Fallback: use first successful result
            synthesis = next((r["result"] for r in results if r.get("success")), "")

    success_count = sum(1 for r in results if r.get("success"))
    logger.info("Swarm complete: %d/%d agents succeeded for task '%s'", success_count, len(active_roles), task[:50])

    return {
        "task": task,
        "agent_results": list(results),
        "synthesis": synthesis,
        "roles_used": active_roles,
        "agents_succeeded": success_count,
    }


async def plan_and_run(task: str) -> dict[str, Any]:
    """
    First run a planner to determine which agents to use, then run those agents.
    """
    # Ask planner which roles are needed
    planner_result = await _call_agent("planner", f"Определи нужные роли для: {task}")
    plan_text = planner_result.get("result", "")

    # Simple role detection from planner output
    roles: list[str] = []
    role_keywords = {
        "researcher": ["исследова", "факт", "поиск", "research"],
        "analyst": ["анализ", "паттерн", "данн", "analysis"],
        "writer": ["написа", "текст", "контент", "write"],
        "critic": ["провер", "ошибк", "улучш", "review"],
    }
    plan_lower = plan_text.lower()
    for role, keywords in role_keywords.items():
        if any(kw in plan_lower for kw in keywords):
            roles.append(role)

    if not roles:
        roles = ["researcher", "writer"]

    return await run_swarm(task, roles=roles)
