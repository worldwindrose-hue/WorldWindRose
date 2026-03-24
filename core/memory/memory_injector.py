"""
ROSA OS — Memory Injector.
Builds [ПАМЯТЬ РОЗЫ] context block to prepend to LLM system prompts.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("rosa.memory.injector")


async def build_memory_context(query: str, session_id: str = "") -> str:
    """Build [ПАМЯТЬ РОЗЫ] block to prepend to LLM system prompt."""
    try:
        from core.memory.eternal import get_eternal_memory
        mem = get_eternal_memory()
        results = await mem.recall(query)

        parts = ["[ПАМЯТЬ РОЗЫ]"]

        # Episodic: past conversations
        episodic = results.get("episodic", [])
        if episodic:
            parts.append("Прошлые разговоры:")
            for item in episodic[:3]:
                text = item.get("text", "")[:200]
                score = item.get("score", 0.0)
                parts.append(f"  - [{score:.2f}] {text}")

        # Graph: known facts
        graph = results.get("graph", [])
        if graph:
            parts.append("Известные факты:")
            for item in graph[:3]:
                subj = item.get("subject_title", item.get("subject", ""))
                pred = item.get("predicate", "related_to")
                obj = item.get("object", "")
                parts.append(f"  - {subj} {pred} {obj}")

        # Session context
        context = results.get("context", {})
        if context:
            ctx_summary_parts = []
            for k, v in list(context.items())[:3]:
                ctx_summary_parts.append(f"{k}: {str(v)[:100]}")
            if ctx_summary_parts:
                parts.append("Текущий контекст:")
                parts.extend(f"  {p}" for p in ctx_summary_parts)

        parts.append("[/ПАМЯТЬ]")
        return "\n".join(parts)

    except Exception as exc:
        logger.warning("build_memory_context failed: %s", exc)
        return ""


async def inject_into_messages(messages: list[dict], query: str) -> list[dict]:
    """Prepend memory context to system message or add as first user message."""
    try:
        memory_block = await build_memory_context(query)
        if not memory_block:
            return messages

        result = list(messages)

        # Look for existing system message
        for i, msg in enumerate(result):
            if msg.get("role") == "system":
                result[i] = {
                    "role": "system",
                    "content": memory_block + "\n\n" + msg.get("content", ""),
                }
                return result

        # No system message: prepend memory as system
        result.insert(0, {"role": "system", "content": memory_block})
        return result

    except Exception as exc:
        logger.warning("inject_into_messages failed: %s", exc)
        return messages
