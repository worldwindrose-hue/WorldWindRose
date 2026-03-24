"""
ROSA OS — Program-Aided Learning (PAL).
Routes math/logic questions through Kimi K2.5 code generation,
then executes the code in an isolated subprocess with a timeout.

Flow:
  1. is_math_query(text) → True
  2. generate_code(text) → Python code string via Kimi
  3. run_code(code) → result string (subprocess, timeout=10s)
  4. Fallback: direct Kimi answer if code execution fails
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

logger = logging.getLogger("rosa.reasoning.pal")

# ── Intent detection ──────────────────────────────────────────────────────────

_MATH_PATTERNS = re.compile(
    r"""
    \b(
        сколько|сколько будет|посчитай|вычисли|рассчитай|реши|найди|
        calculate|compute|solve|evaluate|how many|what is \d|
        integral|derivative|matrix|factorial|fibonacci|prime|
        \d+\s*[\+\-\*\/\^]\s*\d|
        sqrt|log\(|sin\(|cos\(|equation|формул|уравнени
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def is_math_query(text: str) -> bool:
    """Return True if the query is likely a math/logic/computation task."""
    return bool(_MATH_PATTERNS.search(text))


# ── Code generation ───────────────────────────────────────────────────────────

_CODEGEN_PROMPT = """\
You are a Python code generator. The user has a math or logic question.
Write a complete, runnable Python script that:
1. Solves the problem programmatically
2. Prints the final answer as: print("Answer:", result)
3. Uses only standard library (math, itertools, etc.) — no pip installs
4. Handles edge cases
5. Is under 50 lines

Return ONLY the Python code, no markdown fences, no explanation.

Question: {question}"""


async def generate_code(question: str) -> str:
    """Call Kimi K2.5 to generate Python code solving the question."""
    from core.config import get_settings
    import httpx

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise ValueError("No OPENROUTER_API_KEY")

    prompt = _CODEGEN_PROMPT.format(question=question[:500])

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
                "temperature": 0.0,
                "max_tokens": 1024,
            },
        )
        r.raise_for_status()
        code = r.json()["choices"][0]["message"]["content"].strip()

    # Strip markdown fences if present
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

    return code


# ── Isolated execution ────────────────────────────────────────────────────────

def run_code(code: str, timeout: int = 10) -> tuple[bool, str]:
    """
    Execute Python code in an isolated subprocess.
    Returns (success: bool, output: str).
    Uses the firewall to block dangerous patterns before execution.
    """
    from core.security.firewall import check_text, FirewallBlock

    try:
        check_text(code)
    except FirewallBlock as e:
        return False, f"[FIREWALL BLOCKED] {e}"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="rosa_pal_", delete=False
    ) as f:
        f.write(textwrap.dedent(code))
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            # Minimal environment
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": "/tmp",
                "PYTHONPATH": "",
            },
        )
        Path(tmp_path).unlink(missing_ok=True)

        if result.returncode == 0:
            output = result.stdout.strip()
            return True, output if output else "(no output)"
        else:
            return False, result.stderr.strip()[:500]

    except subprocess.TimeoutExpired:
        Path(tmp_path).unlink(missing_ok=True)
        return False, f"[TIMEOUT] Code exceeded {timeout}s"
    except Exception as exc:
        Path(tmp_path).unlink(missing_ok=True)
        return False, f"[ERROR] {exc}"


# ── Main entrypoint ───────────────────────────────────────────────────────────

async def solve(question: str) -> dict:
    """
    Full PAL pipeline:
    1. Generate Python code via Kimi
    2. Execute in sandbox
    3. Return {answer, code, method, success}
    """
    try:
        code = await generate_code(question)
        success, output = await asyncio.get_event_loop().run_in_executor(
            None, lambda: run_code(code)
        )

        if success:
            # Extract answer line if present
            answer = output
            for line in output.split("\n"):
                if line.startswith("Answer:"):
                    answer = line.replace("Answer:", "").strip()
                    break
            return {
                "answer": answer,
                "code": code,
                "method": "pal",
                "success": True,
                "raw_output": output,
            }
        else:
            # Fallback: direct Kimi answer
            logger.debug("PAL code failed (%s), falling back to direct answer", output)
            return await _direct_answer(question, code_error=output)

    except Exception as exc:
        logger.warning("PAL pipeline error: %s", exc)
        return await _direct_answer(question)


async def _direct_answer(question: str, code_error: str = "") -> dict:
    """Fallback: ask Kimi directly without code generation."""
    from core.config import get_settings
    import httpx

    settings = get_settings()
    prompt = f"Answer this math/logic question directly:\n{question}"
    if code_error:
        prompt += f"\n\n(Note: previous code attempt failed: {code_error[:200]})"

    try:
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
                    "temperature": 0.0,
                    "max_tokens": 512,
                },
            )
            r.raise_for_status()
            answer = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        answer = f"Unable to compute: {exc}"

    return {"answer": answer, "code": None, "method": "direct", "success": True}
