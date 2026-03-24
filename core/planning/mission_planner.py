"""
ROSA OS — Mission Planner (Phase 10).

Protocol "Thought → Mission":
1. UNDERSTAND: parse_intent → Mission
2. PLAN: generate_plan → Plan with steps
3. SHOW OWNER: display plan, request approval
4. EXECUTE: execute_plan (after approval)
5. REQUEST PERMISSIONS: if needed, explain and ask

Example: "I want to always be able to talk to you"
→ Plan: setup Telegram bot, ngrok tunnel, LaunchDaemon, etc.
→ Show owner → get approval → execute → notify
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.planning")

_INTENT_PROMPT = """Ты — ROSA OS. Пользователь дал тебе задачу.
Проанализируй её и определи:
1. Что именно хочет пользователь
2. Какие шаги нужны для выполнения
3. Какие разрешения могут потребоваться
4. Оценка сложности (simple/medium/complex/massive)

Задача: {message}

Верни JSON:
{{
  "intent": "Краткое описание цели",
  "steps": [
    {{"id": 1, "title": "...", "description": "...", "requires_permission": false, "permission_reason": ""}},
    ...
  ],
  "permissions_needed": ["...", "..."],
  "complexity": "simple|medium|complex|massive",
  "estimated_duration": "мин/часы/дни"
}}"""

_EXECUTION_PROMPT = """Выполни следующий шаг задачи:
{step_description}

Контекст предыдущих шагов:
{context}

Дай конкретный результат выполнения."""


@dataclass
class MissionStep:
    id: int
    title: str
    description: str
    requires_permission: bool = False
    permission_reason: str = ""
    status: str = "pending"   # pending | approved | running | done | failed | skipped
    result: str = ""
    error: str = ""


@dataclass
class Mission:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    original_message: str = ""
    intent: str = ""
    steps: list[MissionStep] = field(default_factory=list)
    permissions_needed: list[str] = field(default_factory=list)
    complexity: str = "medium"
    estimated_duration: str = ""
    status: str = "planning"   # planning | awaiting_approval | executing | done | cancelled
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# In-memory store for active missions
_missions: dict[str, Mission] = {}


async def _call_model(prompt: str) -> str:
    try:
        from openai import AsyncOpenAI
        from core.config import get_settings
        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
        resp = await client.chat.completions.create(
            model=settings.default_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        raise RuntimeError(f"Model call failed: {exc}") from exc


async def parse_intent(message: str) -> Mission:
    """Step 1: Parse user message into a Mission."""
    try:
        from core.status.tracker import set_status, RosaStatus
        set_status(RosaStatus.THINKING, "Анализирую задачу...")
    except Exception:
        pass

    raw = await _call_model(_INTENT_PROMPT.format(message=message))

    # Strip markdown
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(raw)
    except Exception:
        data = {"intent": message, "steps": [{"id": 1, "title": "Выполнить задачу", "description": message}]}

    steps = [
        MissionStep(
            id=s.get("id", i + 1),
            title=s.get("title", f"Шаг {i + 1}"),
            description=s.get("description", ""),
            requires_permission=s.get("requires_permission", False),
            permission_reason=s.get("permission_reason", ""),
        )
        for i, s in enumerate(data.get("steps", []))
    ]

    mission = Mission(
        original_message=message,
        intent=data.get("intent", message),
        steps=steps,
        permissions_needed=data.get("permissions_needed", []),
        complexity=data.get("complexity", "medium"),
        estimated_duration=data.get("estimated_duration", ""),
        status="awaiting_approval",
    )
    _missions[mission.id] = mission
    logger.info("Mission %s created: %s (%d steps)", mission.id, mission.intent[:50], len(steps))
    return mission


async def approve_mission(mission_id: str, approved_step_ids: list[int] | None = None) -> Mission:
    """Step 3: Owner approves the mission. Optionally skip specific steps."""
    mission = _missions.get(mission_id)
    if not mission:
        raise ValueError(f"Mission not found: {mission_id}")

    mission.status = "executing"
    for step in mission.steps:
        if approved_step_ids is None or step.id in approved_step_ids:
            if step.status == "pending":
                step.status = "approved"
        else:
            step.status = "skipped"

    return mission


async def execute_mission(mission_id: str) -> Mission:
    """Step 4: Execute approved steps."""
    mission = _missions.get(mission_id)
    if not mission:
        raise ValueError(f"Mission not found: {mission_id}")

    context_parts: list[str] = []

    for step in mission.steps:
        if step.status not in ("approved",):
            continue

        step.status = "running"
        try:
            from core.status.tracker import set_status, RosaStatus
            set_status(RosaStatus.ACTING, f"Шаг {step.id}: {step.title}")
        except Exception:
            pass

        context = "\n".join(context_parts[-5:])

        # Check if permissions needed
        if step.requires_permission and step.permission_reason:
            step.result = f"[Требует разрешения: {step.permission_reason}]"
            step.status = "done"
            context_parts.append(f"Шаг {step.id} ({step.title}): требует разрешения — пропущен")
            continue

        try:
            result = await _call_model(
                _EXECUTION_PROMPT.format(
                    step_description=step.description,
                    context=context or "нет",
                )
            )
            step.result = result[:1000]
            step.status = "done"
            context_parts.append(f"Шаг {step.id} ({step.title}): {result[:200]}")
        except Exception as exc:
            step.error = str(exc)
            step.status = "failed"
            logger.error("Step %d failed: %s", step.id, exc)
            context_parts.append(f"Шаг {step.id} ({step.title}): ошибка — {exc}")

    # Check if all done
    all_done = all(s.status in ("done", "failed", "skipped") for s in mission.steps)
    if all_done:
        mission.status = "done"
        mission.completed_at = datetime.now(timezone.utc).isoformat()

        try:
            from core.status.tracker import set_status, RosaStatus
            set_status(RosaStatus.ONLINE, "Миссия завершена")
        except Exception:
            pass

        # Notify via Telegram
        try:
            from core.mobile.telegram_gateway import send_notification
            succeeded = sum(1 for s in mission.steps if s.status == "done")
            await send_notification(f"✅ Миссия завершена: {mission.intent[:80]}\n{succeeded}/{len(mission.steps)} шагов выполнено")
        except Exception:
            pass

    return mission


def get_mission(mission_id: str) -> Mission | None:
    return _missions.get(mission_id)


def list_missions() -> list[dict[str, Any]]:
    return [m.to_dict() for m in _missions.values()]


def cancel_mission(mission_id: str) -> bool:
    m = _missions.get(mission_id)
    if m:
        m.status = "cancelled"
        return True
    return False
