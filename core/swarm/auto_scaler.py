"""
ROSA OS — Auto-Scaling Swarm (Phase 8).

Rosa decides how many agents to spawn based on task complexity.
Supports specialized agent types: Research, Code, Parse, Memory, File, Monitor.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("rosa.swarm.auto_scaler")

MAX_AGENTS = 20

# Complexity → agent count
_COMPLEXITY_MAP = {
    "simple": 1,
    "medium": 3,
    "complex": 8,
    "massive": 15,
}

# Agent role system prompts
_AGENT_SYSTEM_PROMPTS = {
    "researcher": "Ты — агент-исследователь. Находи и систематизируй факты. Будь конкретен и дай источники.",
    "code": "Ты — агент-разработчик. Пиши чистый, рабочий Python код с тестами.",
    "parser": "Ты — агент-парсер. Извлекай структурированные данные из текста. Возвращай JSON.",
    "memory": "Ты — агент памяти. Извлекай ключевые факты и концепты для сохранения в граф знаний.",
    "file": "Ты — агент файловой системы. Анализируй структуру файлов и директорий.",
    "monitor": "Ты — агент мониторинга. Отслеживай метрики и выявляй аномалии.",
    "analyst": "Ты — агент-аналитик. Анализируй данные, находи паттерны и инсайты.",
    "critic": "Ты — агент-критик. Находи слабые места и предлагай улучшения.",
    "planner": "Ты — агент-планировщик. Декомпозируй задачи на конкретные шаги.",
}


@dataclass
class AgentTask:
    agent_id: str
    role: str
    subtask: str
    status: str = "pending"   # pending | running | done | failed
    result: str = ""
    error: str = ""


def classify_complexity(task: str) -> str:
    """Classify task complexity based on heuristics."""
    t = task.lower()
    words = len(task.split())

    # Simple: short questions
    if words <= 10 and not any(kw in t for kw in ["анализ", "исследование", "парс", "поиск", "код"]):
        return "simple"

    # Massive: research/parsing tasks
    if any(kw in t for kw in ["полный анализ", "все данные", "парс весь", "исследование рынка", "comprehensive"]):
        return "massive"

    # Complex: multi-step with dependencies
    if any(kw in t for kw in ["разработай", "создай систему", "построй", "проанализируй и", "исследуй"]):
        return "complex"

    return "medium"


def decide_agent_count(task: str) -> int:
    complexity = classify_complexity(task)
    return min(_COMPLEXITY_MAP.get(complexity, 3), MAX_AGENTS)


def decide_agent_roles(task: str, count: int) -> list[str]:
    """Decide which agent roles to use based on task content."""
    t = task.lower()
    roles: list[str] = []

    if any(kw in t for kw in ["найди", "исследуй", "поиск", "research"]):
        roles.append("researcher")
    if any(kw in t for kw in ["код", "скрипт", "функция", "python", "code"]):
        roles.append("code")
    if any(kw in t for kw in ["данные", "таблица", "парс", "extract"]):
        roles.append("parser")
    if any(kw in t for kw in ["запомни", "сохрани", "факты", "память"]):
        roles.append("memory")
    if any(kw in t for kw in ["файл", "директория", "проект"]):
        roles.append("file")
    if any(kw in t for kw in ["анализ", "паттерн", "тренд"]):
        roles.append("analyst")

    # Always include critic and planner for complex tasks
    if count >= 5:
        roles.extend(["critic", "planner"])

    # Deduplicate, fallback
    roles = list(dict.fromkeys(roles))  # preserve order, deduplicate
    if not roles:
        roles = ["researcher", "analyst", "critic"]

    return roles[:count]


async def _run_agent(agent_task: AgentTask, context: str = "") -> AgentTask:
    """Run a single agent and update its status."""
    agent_task.status = "running"
    system = _AGENT_SYSTEM_PROMPTS.get(agent_task.role, "Ты — агент-помощник.")

    try:
        from openai import AsyncOpenAI
        from core.config import get_settings
        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
        messages = [{"role": "system", "content": system}]
        if context:
            messages.append({"role": "user", "content": f"Контекст:\n{context}\n\nЗадача: {agent_task.subtask}"})
        else:
            messages.append({"role": "user", "content": agent_task.subtask})

        resp = await client.chat.completions.create(
            model=settings.default_model,
            messages=messages,
            max_tokens=1024,
        )
        agent_task.result = resp.choices[0].message.content or ""
        agent_task.status = "done"
    except Exception as exc:
        agent_task.error = str(exc)
        agent_task.status = "failed"
        logger.warning("Agent %s (%s) failed: %s", agent_task.agent_id, agent_task.role, exc)

    return agent_task


async def auto_run(
    task: str,
    context: str = "",
    max_agents: int | None = None,
) -> dict[str, Any]:
    """
    Auto-determine agent count and roles, run swarm, synthesize.
    """
    count = min(decide_agent_count(task), max_agents or MAX_AGENTS)
    roles = decide_agent_roles(task, count)

    try:
        from core.status.tracker import set_status, RosaStatus
        set_status(RosaStatus.SWARMING, f"Рой: {len(roles)} агентов", agents=len(roles))
    except Exception:
        pass

    # Build agent tasks
    agent_tasks = [
        AgentTask(
            agent_id=f"agent_{i}_{role}",
            role=role,
            subtask=f"{task} (фокус: {role})",
        )
        for i, role in enumerate(roles)
    ]

    # Run all in parallel
    completed = await asyncio.gather(*[_run_agent(a, context) for a in agent_tasks])

    # Synthesize
    results_text = "\n\n".join(
        f"**{a.role.upper()} [{a.agent_id}]:**\n{a.result}"
        for a in completed
        if a.status == "done" and a.result
    )

    synthesis = ""
    if results_text:
        try:
            from openai import AsyncOpenAI
            from core.config import get_settings
            settings = get_settings()
            client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
            prompt = f"Задача: {task}\n\nРезультаты агентов:\n{results_text}\n\nСинтезируй финальный ответ:"
            resp = await client.chat.completions.create(
                model=settings.default_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            synthesis = resp.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("Synthesis failed: %s", exc)
            synthesis = results_text[:2000]

    try:
        from core.status.tracker import set_status, RosaStatus
        set_status(RosaStatus.ONLINE, "Готова к работе")
    except Exception:
        pass

    return {
        "task": task,
        "agent_count": len(completed),
        "roles": roles,
        "complexity": classify_complexity(task),
        "agent_results": [
            {"id": a.agent_id, "role": a.role, "status": a.status, "result": a.result[:500]}
            for a in completed
        ],
        "synthesis": synthesis,
        "agents_succeeded": sum(1 for a in completed if a.status == "done"),
    }
