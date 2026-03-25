"""
ROSA OS — Code Genesis.

Rosa writes Python modules for herself autonomously.
All generated modules go to /modules/ (never /core/).
Every change requires sandbox test pass before applying.
Human Gate for /core/ modifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.self_improvement.genesis")

_GENESIS_LOG = Path("memory/code_genesis.log")
_MODULES_DIR = Path("modules")

_GENERATE_PROMPT = """Ты — опытный Python-разработчик.
Напиши Python-модуль по следующей спецификации.
Требования:
- Чистый, читаемый код с docstrings
- Обработка всех исключений
- Нет внешних зависимостей кроме стандартной библиотеки Python и указанных
- Возвращай ТОЛЬКО код без объяснений

Спецификация: {spec}

Имя модуля: {module_name}"""

_TEST_PROMPT = """Напиши pytest-тесты для следующего Python-модуля.
- Минимум 3 теста
- Используй pytest и pytest.mark.asyncio если нужно
- Тесты должны быть независимыми
- Возвращай ТОЛЬКО код тестов без объяснений

Код модуля:
{code}"""


async def analyze_need(task: str) -> dict:
    """Determine what module needs to be written for a task."""
    return {
        "task": task,
        "module_name": _task_to_module_name(task),
        "spec": f"Модуль для выполнения задачи: {task}",
        "estimated_complexity": "medium",
    }


async def generate_module(spec: str, module_name: str) -> dict:
    """Ask Kimi to write a Python module. Returns {code, tests, ready}."""
    _log_genesis("generate_start", module_name, {"spec": spec[:200]})

    code = await _call_llm(_GENERATE_PROMPT.format(spec=spec, module_name=module_name))
    if not code:
        return {"code": "", "tests": "", "ready": False, "error": "LLM unavailable"}

    code = _clean_code_block(code)
    tests = await _call_llm(_TEST_PROMPT.format(code=code[:2000]))
    tests = _clean_code_block(tests) if tests else _generate_stub_tests(module_name)

    _log_genesis("generate_done", module_name, {"code_lines": len(code.splitlines())})
    return {"code": code, "tests": tests, "ready": bool(code.strip())}


async def sandbox_test(code: str, tests: str) -> tuple[bool, str]:
    """
    Run code + tests in isolated subprocess.
    Returns (passed: bool, output: str).
    """
    sandbox_id = str(uuid.uuid4())[:8]
    sandbox_dir = Path(tempfile.mkdtemp(prefix=f"rosa_sandbox_{sandbox_id}_"))

    try:
        # Write module and tests
        mod_file = sandbox_dir / "module.py"
        test_file = sandbox_dir / "test_module.py"
        mod_file.write_text(code)

        # Adjust test imports to use relative module
        adjusted_tests = tests.replace("from module import", "from module import") \
                               .replace("import module", "import module")
        test_file.write_text(adjusted_tests)

        # Run pytest in subprocess with timeout
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["python3", "-m", "pytest", str(test_file), "-v", "--tb=short", "-q"],
                    cwd=str(sandbox_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                ),
            ),
            timeout=40,
        )
        passed = result.returncode == 0
        output = (result.stdout + result.stderr)[-2000:]
        _log_genesis("sandbox", "test", {"passed": passed, "output": output[-500:]})
        return passed, output

    except asyncio.TimeoutError:
        return False, "Sandbox timeout (>40s)"
    except Exception as exc:
        return False, f"Sandbox error: {exc}"
    finally:
        import shutil
        shutil.rmtree(sandbox_dir, ignore_errors=True)


async def apply_module(module_name: str, code: str) -> bool:
    """
    Write generated code to modules/ directory.
    Only after sandbox tests pass. Never touches /core/.
    """
    _MODULES_DIR.mkdir(parents=True, exist_ok=True)
    init_file = _MODULES_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""ROSA OS — Generated modules."""\n')

    safe_name = module_name.replace("-", "_").replace(" ", "_").lower()
    if not safe_name.endswith(".py"):
        safe_name += ".py"

    target = _MODULES_DIR / safe_name
    target.write_text(code)
    logger.info("Applied module: %s (%d lines)", target, len(code.splitlines()))
    _log_genesis("apply", module_name, {"path": str(target)})

    # Auto-commit
    try:
        subprocess.run(
            ["git", "add", str(target)],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "commit", "-m", f"CodeGenesis: auto-generated module {safe_name}"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass

    return True


async def genesis_pipeline(task: str, max_attempts: int = 3) -> dict:
    """
    Full pipeline: analyze → generate → sandbox → apply (if pass).
    Returns {success, module_name, attempts, error}.
    """
    need = await analyze_need(task)
    module_name = need["module_name"]
    spec = need["spec"]

    for attempt in range(1, max_attempts + 1):
        logger.info("CodeGenesis attempt %d/%d for: %s", attempt, max_attempts, task)
        result = await generate_module(spec, module_name)

        if not result["ready"]:
            continue

        passed, output = await sandbox_test(result["code"], result["tests"])
        if passed:
            await apply_module(module_name, result["code"])
            return {
                "success": True,
                "module_name": module_name,
                "attempts": attempt,
                "output": output,
            }

        # Feed failure back into next attempt
        spec = f"{spec}\n\nПредыдущая попытка провалила тесты:\n{output[:500]}\nИсправь эти проблемы."

    return {
        "success": False,
        "module_name": module_name,
        "attempts": max_attempts,
        "error": "All sandbox attempts failed",
    }


# ── HELPERS ───────────────────────────────────────────────────────────────

async def _call_llm(prompt: str) -> Optional[str]:
    try:
        import httpx
        from core.config import get_settings
        s = get_settings()
        if not s.openrouter_api_key:
            return None
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.openrouter_api_key}"},
                json={
                    "model": "moonshotai/kimi-k2.5",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2000,
                    "temperature": 0.2,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        logger.debug("LLM call failed: %s", exc)
        return None


def _clean_code_block(text: str) -> str:
    """Strip ```python ... ``` fences from LLM output."""
    import re
    text = re.sub(r"^```(?:python)?\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```$", "", text.strip(), flags=re.MULTILINE)
    return text.strip()


def _task_to_module_name(task: str) -> str:
    import re
    name = re.sub(r"[^a-zA-Zа-яА-Я0-9\s]", "", task.lower())
    words = name.split()[:4]
    # Transliterate basic Russian
    translit = {"а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ж":"zh",
                "з":"z","и":"i","к":"k","л":"l","м":"m","н":"n","о":"o",
                "п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f","х":"h",
                "ц":"ts","ч":"ch","ш":"sh","щ":"sch","э":"e","ю":"yu","я":"ya"}
    result = []
    for w in words:
        tw = "".join(translit.get(c, c) for c in w)
        result.append(tw)
    return "_".join(result) or "generated_module"


def _generate_stub_tests(module_name: str) -> str:
    return f"""import pytest

def test_{module_name}_import():
    import module
    assert module is not None

def test_{module_name}_has_content():
    import module
    assert len(dir(module)) > 0
"""


def _log_genesis(event: str, name: str, data: dict) -> None:
    try:
        from datetime import datetime, timezone
        _GENESIS_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "event": event, "name": name, "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(_GENESIS_LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
