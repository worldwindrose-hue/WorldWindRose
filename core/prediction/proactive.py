"""
ROSA OS — Proactive Scheduler.

Runs background async tasks to deliver morning briefings,
check subscriptions, and trigger habit-based suggestions.

Default: morning briefing at 07:00 local time.
Subscriptions: checked on their configured schedule.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.prediction.proactive")

_scheduler_task: asyncio.Task | None = None
_running = False


async def _morning_briefing() -> dict[str, Any]:
    """
    Generate a morning briefing by querying:
    - Top habit predictions for the day
    - Pending tasks from DB
    - Any active subscriptions with fresh content
    """
    from core.prediction.habit_graph import get_habit_graph
    now = datetime.now()
    graph = get_habit_graph()
    predictions = graph.predict_next_task(now.hour, now.weekday())

    # Pending tasks
    pending_tasks: list[dict] = []
    try:
        from core.memory.store import get_store
        store = await get_store()
        tasks = await store.list_tasks(status="pending")
        pending_tasks = [{"title": t.title, "priority": getattr(t, "priority", 2)} for t in tasks[:5]]
    except Exception as exc:
        logger.debug("Could not load pending tasks: %s", exc)

    briefing = {
        "type": "morning_briefing",
        "timestamp": now.isoformat(),
        "predictions": predictions[:3],
        "pending_tasks": pending_tasks,
        "message": _format_briefing(now, predictions, pending_tasks),
    }
    logger.info("Morning briefing generated: %d predictions, %d tasks", len(predictions), len(pending_tasks))
    return briefing


def _format_briefing(
    now: datetime,
    predictions: list[dict],
    tasks: list[dict],
) -> str:
    lines = [f"Доброе утро! {now.strftime('%A, %d %B %Y')}"]
    if predictions:
        top = predictions[0]["task_type"]
        lines.append(f"Вероятно, сегодня вас интересует: {top}")
    if tasks:
        lines.append(f"Незавершённых задач: {len(tasks)}")
        for t in tasks[:3]:
            lines.append(f"  • {t['title']}")
    lines.append("Чем могу помочь?")
    return "\n".join(lines)


async def check_subscriptions() -> list[dict[str, Any]]:
    """Check all enabled subscriptions and return fresh content summaries."""
    results = []
    try:
        from core.memory.store import get_store
        store = await get_store()
        subs = await store.list_subscriptions(enabled_only=True)
        for sub in subs:
            try:
                result = await _fetch_subscription(sub)
                if result:
                    results.append(result)
                    await store.touch_subscription(sub.id)
            except Exception as exc:
                logger.debug("Subscription %s check failed: %s", sub.id, exc)
    except Exception as exc:
        logger.debug("list_subscriptions failed: %s", exc)
    return results


async def _fetch_subscription(sub: Any) -> dict[str, Any] | None:
    """Fetch content for a single subscription based on source_type."""
    source_type = getattr(sub, "source_type", "")
    source_url = getattr(sub, "source_url", "")
    keywords = getattr(sub, "keywords", "[]")

    if not source_url:
        return None

    if source_type == "rss":
        return await _fetch_rss(sub.name, source_url)
    elif source_type == "github":
        return {"name": sub.name, "type": "github", "url": source_url, "note": "GitHub check pending"}
    elif source_type == "tiktok":
        return {"name": sub.name, "type": "tiktok", "url": source_url, "note": "TikTok check pending"}
    return None


async def _fetch_rss(name: str, url: str) -> dict[str, Any] | None:
    """Minimal RSS fetch via httpx."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            # Very basic title extraction
            import re
            titles = re.findall(r"<title>(.*?)</title>", r.text)
            return {
                "name": name,
                "type": "rss",
                "url": url,
                "items": titles[1:4] if len(titles) > 1 else [],
            }
    except Exception as exc:
        logger.debug("RSS fetch failed for %s: %s", url, exc)
        return None


async def _scheduler_loop() -> None:
    """Main scheduler loop — runs continuously until stopped."""
    global _running
    logger.info("Proactive scheduler started")

    while _running:
        now = datetime.now()

        # Morning briefing at 07:00
        if now.hour == 7 and now.minute == 0:
            try:
                from core.status.tracker import set_status, RosaStatus
                set_status(RosaStatus.ACTING, "Генерирую утренний брифинг")
            except Exception:
                pass
            try:
                briefing = await _morning_briefing()
                logger.info("Morning briefing: %s", briefing["message"][:80])
            except Exception as exc:
                logger.error("Morning briefing failed: %s", exc)

        # Check subscriptions every hour at :30
        if now.minute == 30:
            try:
                await check_subscriptions()
            except Exception as exc:
                logger.error("Subscription check failed: %s", exc)

        # Sleep until next minute
        await asyncio.sleep(60)


def start_scheduler() -> None:
    """Start the background scheduler loop (idempotent)."""
    global _scheduler_task, _running
    if _running:
        logger.debug("Scheduler already running")
        return
    _running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("Proactive scheduler task created")


def stop_scheduler() -> None:
    """Stop the background scheduler."""
    global _scheduler_task, _running
    _running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        _scheduler_task = None
    logger.info("Proactive scheduler stopped")


def is_running() -> bool:
    return _running and _scheduler_task is not None and not _scheduler_task.done()


async def get_briefing_now() -> dict[str, Any]:
    """Generate an on-demand briefing (not waiting for 07:00)."""
    return await _morning_briefing()


# ═══════════════════════════════════════════════════════════════════════════
# ProactiveProblemSolver — "Роза никогда не сдаётся без боя"
# ═══════════════════════════════════════════════════════════════════════════

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ProblemSolverResult:
    problem: str
    solved: bool
    solution: str = ""
    iterations: int = 0
    actions_taken: list[str] = field(default_factory=list)
    explanation: str = ""
    alternatives: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


class ProactiveProblemSolver:
    """
    Autonomous problem solver. Never gives up without trying.

    Principle: when any error/failure occurs, instead of returning it raw:
      1. Classify the problem
      2. Find a solution (Knowledge Graph + LLM search)
      3. Try the solution
      4. If solved: save to graph + return fixed result
      5. If not solved: explain clearly + propose concrete alternatives

    Limits: max 5 iterations, max 3 minutes per problem.
    """

    MAX_ITERATIONS = 5
    TIMEOUT_SECONDS = 180

    def __init__(self, status_cb: Optional[Callable[[str], None]] = None):
        self._cb = status_cb or (lambda msg: logger.info("[Solver] %s", msg))

    async def autonomy_loop(
        self,
        problem: str,
        context: dict | None = None,
        original_task: str = "",
    ) -> ProblemSolverResult:
        """
        Main autonomous loop. Tries to solve the problem within limits.
        """
        import time
        t0 = time.monotonic()
        ctx = context or {}
        actions: list[str] = []
        result = ProblemSolverResult(problem=problem, solved=False)

        self._cb(f"🔍 Классифицирую проблему: {problem[:60]}")

        # Step 1: Classify
        category = self._classify(problem)
        self._cb(f"📂 Категория: {category}")

        # Step 2: Check Knowledge Graph for known solution
        self._cb("📚 Проверяю граф знаний...")
        known = await self._lookup_knowledge_graph(problem, category)
        if known:
            self._cb(f"💡 Найдено готовое решение: {known[:60]}")
            actions.append(f"Found in knowledge graph: {known[:60]}")
            result.solution = known
            result.solved = True
            result.iterations = 1
            result.actions_taken = actions
            result.duration_ms = round((time.monotonic() - t0) * 1000, 1)
            return result

        # Steps 3-5: Iterative search and apply
        for i in range(self.MAX_ITERATIONS):
            if (time.monotonic() - t0) > self.TIMEOUT_SECONDS:
                self._cb(f"⏱️ Таймаут {self.TIMEOUT_SECONDS}s")
                break

            self._cb(f"🤖 Итерация {i+1}/{self.MAX_ITERATIONS}: ищу решение...")
            solution = await self._find_solution(problem, category, ctx, i)
            actions.append(f"Iter {i+1}: tried '{solution[:50]}'")

            self._cb(f"⚙️ Применяю: {solution[:60]}")
            success, outcome = await self._apply_solution(solution, problem, ctx, original_task)

            if success:
                self._cb(f"✅ Решено на итерации {i+1}!")
                await self._save_to_knowledge_graph(problem, category, solution)
                self._cb("📚 Сохраняю решение в память...")
                result.solved = True
                result.solution = outcome
                result.iterations = i + 1
                result.actions_taken = actions
                result.duration_ms = round((time.monotonic() - t0) * 1000, 1)
                return result

            self._cb(f"❌ Итерация {i+1} не сработала: {outcome[:50]}")

        # Step 5: Failure — explain and propose alternatives
        self._cb("💬 Формирую объяснение и альтернативы...")
        explanation, alternatives = await self._explain_and_propose(problem, category, actions)
        result.explanation = explanation
        result.alternatives = alternatives
        result.iterations = min(self.MAX_ITERATIONS, len(actions))
        result.actions_taken = actions
        result.duration_ms = round((time.monotonic() - t0) * 1000, 1)
        self._cb(f"🏳️ Задача не решена автономно: {explanation[:80]}")
        return result

    def _classify(self, problem: str) -> str:
        """Classify problem type for targeted solving."""
        p = problem.lower()
        if any(k in p for k in ["download", "parse", "instagram", "tiktok", "youtube"]):
            return "media_download"
        if any(k in p for k in ["import", "module", "not found", "modulenotfounderror"]):
            return "missing_dependency"
        if any(k in p for k in ["connection", "timeout", "network", "ssl", "http"]):
            return "network_error"
        if any(k in p for k in ["permission", "access denied", "forbidden", "403"]):
            return "permission_error"
        if any(k in p for k in ["database", "sqlite", "sql", "db"]):
            return "database_error"
        if any(k in p for k in ["api", "key", "401", "unauthorized"]):
            return "auth_error"
        return "general_error"

    async def _lookup_knowledge_graph(self, problem: str, category: str) -> Optional[str]:
        """Check if we have a saved solution."""
        try:
            from core.memory.eternal import get_eternal_memory
            mem = get_eternal_memory()
            key = f"solver:{category}:{problem[:30]}"
            for msg in list(mem.working._messages):
                if key in msg:
                    return msg.split(": ", 2)[-1]
        except Exception:
            pass
        return None

    async def _save_to_knowledge_graph(self, problem: str, category: str, solution: str) -> None:
        """Persist solution for future reuse."""
        try:
            from core.memory.eternal import get_eternal_memory
            mem = get_eternal_memory()
            key = f"solver:{category}:{problem[:30]}"
            await mem.working.add(f"[SOLVER_SOLUTION] {key}: {solution}")
        except Exception as exc:
            logger.debug("Could not save solution: %s", exc)

    async def _find_solution(
        self, problem: str, category: str, ctx: dict, iteration: int
    ) -> str:
        """Ask LLM for a solution based on problem category."""
        try:
            from core.router.local_router import get_local_router
            router = get_local_router()
            resp = await router.route([{
                "role": "user",
                "content": (
                    f"Problem: {problem}\nCategory: {category}\n"
                    f"Context: {ctx}\nIteration: {iteration+1}\n\n"
                    "Provide ONE specific actionable solution as a single sentence. "
                    "No explanations, just the solution. Start with an action verb."
                )
            }], max_tokens=150)
            return resp.content.strip()
        except Exception as exc:
            return f"Retry with different parameters: {str(exc)[:50]}"

    async def _apply_solution(
        self, solution: str, problem: str, ctx: dict, original_task: str
    ) -> tuple[bool, str]:
        """
        Attempt to apply the solution. Returns (success, outcome).
        For now: validates solution plausibility and simulates application.
        Extend this method with actual execution logic per category.
        """
        # Media download: delegate to smart_parser
        if "instagram" in problem.lower() or "tiktok" in problem.lower() or "youtube" in problem.lower():
            url = ctx.get("url", "")
            if url:
                try:
                    from core.agents.smart_parser import smart_parse
                    parse_result = await smart_parse(url, context=original_task, status_cb=self._cb)
                    if parse_result.success:
                        return True, parse_result.content or parse_result.media_path or "Success"
                    return False, parse_result.explanation[:100]
                except Exception as exc:
                    return False, str(exc)[:100]

        # Missing dependency
        if "missing_dependency" in problem or "ModuleNotFoundError" in problem:
            import re
            m = re.search(r"No module named ['\"]([^'\"]+)['\"]", problem)
            if m:
                pkg = m.group(1).replace("_", "-")
                import subprocess
                res = subprocess.run(["pip3", "install", pkg, "-q"], capture_output=True, timeout=60)
                if res.returncode == 0:
                    return True, f"Installed {pkg} successfully"
                return False, f"pip install {pkg} failed: {res.stderr.decode()[:80]}"

        # For other categories: heuristic success simulation based on solution quality
        if len(solution) > 20 and any(w in solution.lower() for w in ["try", "use", "install", "add", "set"]):
            return False, f"Solution noted but requires manual implementation: {solution[:60]}"

        return False, "Could not automatically apply this solution"

    async def _explain_and_propose(
        self, problem: str, category: str, actions: list[str]
    ) -> tuple[str, list[str]]:
        """Generate human-friendly explanation and concrete alternatives."""
        tried = "; ".join(a[:40] for a in actions[:3])
        explanation = (
            f"Автономный поиск завершён ({len(actions)} попыток).\n"
            f"Проблема: {problem[:100]}\n"
            f"Категория: {category}\n"
            f"Попробовала: {tried}"
        )
        alternatives = {
            "media_download": [
                "Предоставь cookies браузера для авторизованного доступа",
                "Используй VPN если контент ограничен по региону",
                "Для закрытых аккаунтов нужен аккаунт с доступом",
            ],
            "missing_dependency": [
                "Запусти: pip3 install <имя_пакета>",
                "Проверь виртуальное окружение: which python3",
            ],
            "network_error": [
                "Проверь интернет-соединение",
                "Попробуй через VPN",
                "Сервис может быть временно недоступен",
            ],
            "auth_error": [
                "Проверь API ключ в .env файле",
                "Обнови токен если истёк срок",
            ],
        }.get(category, ["Опиши проблему подробнее", "Проверь логи в memory/"])
        return explanation, alternatives


_problem_solver: ProactiveProblemSolver | None = None


def get_problem_solver(status_cb: Optional[Callable[[str], None]] = None) -> ProactiveProblemSolver:
    """Get or create ProactiveProblemSolver instance."""
    global _problem_solver
    if _problem_solver is None or status_cb is not None:
        _problem_solver = ProactiveProblemSolver(status_cb=status_cb)
    return _problem_solver


async def solve_problem(
    problem: str,
    context: dict | None = None,
    original_task: str = "",
    status_cb: Optional[Callable[[str], None]] = None,
) -> ProblemSolverResult:
    """Convenience function: solve a problem autonomously."""
    solver = ProactiveProblemSolver(status_cb=status_cb)
    return await solver.autonomy_loop(problem, context, original_task)
