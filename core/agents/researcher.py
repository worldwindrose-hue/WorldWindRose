"""
ROSA OS — Research Agent.

Multi-step research pipeline:
1. Break research question into sub-queries
2. Search web for each sub-query
3. Extract key facts
4. Add to knowledge graph
5. Synthesize final report
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("rosa.agents.researcher")

_DECOMPOSE_PROMPT = """Ты — исследовательский агент. Разбей следующий вопрос на 3-5 конкретных под-запросов для поиска.
Верни только JSON массив строк: ["запрос1", "запрос2", ...]

Вопрос: {question}"""

_EXTRACT_PROMPT = """Из следующего текста извлеки 3-5 ключевых фактов.
Верни JSON: {{"facts": ["факт1", "факт2", ...], "source_quality": 0.7}}

Текст: {text}"""

_SYNTHESIS_PROMPT = """На основе собранных фактов напиши исчерпывающий ответ на вопрос.
Структурируй с заголовками. Используй только предоставленные факты.

Вопрос: {question}

Факты:
{facts}"""


async def _call_kimi(prompt: str, json_mode: bool = False) -> str:
    """Call Kimi K2.5 for reasoning steps."""
    from openai import AsyncOpenAI
    from core.config import get_settings
    settings = get_settings()

    client = AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    kwargs: dict[str, Any] = {
        "model": settings.default_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    resp = await client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


async def _web_search(query: str) -> list[str]:
    """
    Search the web for a query.
    Uses tools.py WebSearchTool if available, else returns empty list.
    """
    try:
        from tools import WebSearchTool
        tool = WebSearchTool()
        result = tool.run(query)
        # Parse result string into list of snippets
        lines = [line.strip() for line in result.split("\n") if line.strip()]
        return lines[:5]
    except Exception as exc:
        logger.debug("Web search failed for '%s': %s", query, exc)
        return []


async def research(question: str, session_id: str = "research") -> dict[str, Any]:
    """
    Full research pipeline for a question.

    Returns:
        {"question": str, "report": str, "facts": list, "nodes_created": int, "queries_run": int}
    """
    import json

    # Step 1: Decompose into sub-queries
    decompose_response = await _call_kimi(
        _DECOMPOSE_PROMPT.format(question=question),
        json_mode=False,
    )

    sub_queries: list[str] = []
    try:
        # Try to parse JSON from response
        import re
        json_match = re.search(r"\[.*?\]", decompose_response, re.DOTALL)
        if json_match:
            sub_queries = json.loads(json_match.group())
    except Exception:
        pass

    if not sub_queries:
        sub_queries = [question]

    logger.info("Research: %d sub-queries for '%s'", len(sub_queries), question[:50])

    # Step 2: Search + extract facts for each sub-query
    all_facts: list[str] = []
    nodes_created = 0

    for query in sub_queries[:5]:
        snippets = await _web_search(query)

        if snippets:
            combined = "\n".join(snippets[:3])
            try:
                extract_response = await _call_kimi(
                    _EXTRACT_PROMPT.format(text=combined),
                    json_mode=False,
                )
                extract_json = re.search(r"\{.*\}", extract_response, re.DOTALL)
                if extract_json:
                    data = json.loads(extract_json.group())
                    facts = data.get("facts", [])
                    all_facts.extend(facts)

                    # Add to knowledge graph
                    try:
                        from core.knowledge.graph import add_insight
                        for fact in facts:
                            r = await add_insight(
                                text=fact,
                                metadata={"source": "web_research", "query": query},
                                session_id=session_id,
                            )
                            nodes_created += r.get("nodes_created", 0)
                    except Exception as exc:
                        logger.debug("Graph ingest failed: %s", exc)
            except Exception as exc:
                logger.debug("Fact extraction failed for '%s': %s", query, exc)

    # Step 3: Synthesize final report
    if all_facts:
        facts_text = "\n".join(f"- {f}" for f in all_facts[:20])
        report = await _call_kimi(
            _SYNTHESIS_PROMPT.format(question=question, facts=facts_text)
        )
    else:
        # Direct answer without search facts
        report = await _call_kimi(f"Ответь на вопрос подробно: {question}")

    return {
        "question": question,
        "report": report,
        "facts": all_facts,
        "nodes_created": nodes_created,
        "queries_run": len(sub_queries),
        "session_id": session_id,
    }
