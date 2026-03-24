"""
ROSA OS — Self-Coder (Phase 7).

Rosa can write, test, and commit Python modules autonomously.
All operations go through the safety sandbox.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.coding.self_coder")

_WRITE_MODULE_PROMPT = """Напиши Python модуль для следующей задачи:
{task}

Требования:
- Чистый, читаемый код
- Docstrings для публичных функций
- Обработка ошибок
- Без внешних зависимостей кроме стандартных

Верни ТОЛЬКО код Python без markdown-блоков."""

_TEST_PROMPT = """Напиши pytest тесты для этого Python модуля:
{code}

Требования:
- Минимум 3 теста
- Используй только стандартный pytest
- Мок для внешних зависимостей

Верни ТОЛЬКО код тестов без markdown-блоков."""

_REFACTOR_PROMPT = """Отрефактори этот Python код согласно инструкции.
Инструкция: {instruction}

Текущий код:
{code}

Верни ТОЛЬКО улучшенный код без markdown-блоков."""


async def _call_model(prompt: str, max_tokens: int = 2048) -> str:
    try:
        from openai import AsyncOpenAI
        from core.config import get_settings
        settings = get_settings()
        client = AsyncOpenAI(api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url)
        resp = await client.chat.completions.create(
            model=settings.default_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        raise RuntimeError(f"Model call failed: {exc}") from exc


async def write_module(path: str | Path, task: str, auto_test: bool = True) -> dict[str, Any]:
    """
    Generate a Python module from a task description.
    Runs tests if auto_test=True. Saves to path.
    """
    try:
        from core.status.tracker import set_status, RosaStatus
        set_status(RosaStatus.ACTING, f"Пишу модуль: {task[:60]}")
    except Exception:
        pass

    # Generate code
    code = await _call_model(_WRITE_MODULE_PROMPT.format(task=task))

    # Strip markdown if present
    if "```python" in code:
        code = code.split("```python")[1].split("```")[0].strip()
    elif "```" in code:
        code = code.split("```")[1].split("```")[0].strip()

    # Write to path
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(code, encoding="utf-8")
    logger.info("Module written: %s (%d bytes)", p, len(code))

    # Run tests
    test_result = None
    if auto_test:
        test_code = await _call_model(_TEST_PROMPT.format(code=code))
        if "```python" in test_code:
            test_code = test_code.split("```python")[1].split("```")[0].strip()

        test_path = p.parent / f"test_{p.stem}.py"
        test_path.write_text(test_code, encoding="utf-8")

        from core.coding.code_executor import execute_bash
        success, output = await execute_bash(f"python3 -m pytest {test_path} -v --tb=short 2>&1")
        test_result = {"success": success, "output": output[:2000], "test_file": str(test_path)}

    return {
        "path": str(p),
        "code_length": len(code),
        "test_result": test_result,
        "task": task,
    }


async def refactor_module(path: str | Path, instruction: str) -> dict[str, Any]:
    """Refactor an existing module according to instruction."""
    p = Path(path)
    if not p.exists():
        return {"success": False, "error": f"File not found: {p}"}

    original = p.read_text(encoding="utf-8")
    refactored = await _call_model(_REFACTOR_PROMPT.format(instruction=instruction, code=original))

    # Strip markdown
    if "```python" in refactored:
        refactored = refactored.split("```python")[1].split("```")[0].strip()

    # Safety check: must still be valid Python
    try:
        compile(refactored, "<string>", "exec")
    except SyntaxError as e:
        return {"success": False, "error": f"Syntax error in refactored code: {e}"}

    # Backup original
    backup = p.with_suffix(".py.bak")
    backup.write_text(original, encoding="utf-8")

    p.write_text(refactored, encoding="utf-8")
    logger.info("Refactored: %s", p)

    return {
        "success": True,
        "path": str(p),
        "backup": str(backup),
        "original_length": len(original),
        "refactored_length": len(refactored),
    }


async def execute_and_explain(code: str, language: str = "python") -> dict[str, Any]:
    """Execute code and have Rosa explain the output."""
    from core.coding.code_executor import execute_code
    result = await execute_code(language, code)

    if result["output"] and len(result["output"]) > 10:
        try:
            explanation = await _call_model(
                f"Объясни результат выполнения этого кода:\n\nКод:\n{code}\n\nВывод:\n{result['output']}"
            )
            result["explanation"] = explanation
        except Exception:
            pass

    return result
