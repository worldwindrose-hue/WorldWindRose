"""
ROSA OS — Content Pipeline Agent.

Multi-step content creation:
1. Research topic (via researcher agent)
2. Generate outline
3. Write draft
4. Review & polish

Supports: blog posts, social posts, summaries, scripts.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("rosa.agents.content")

_OUTLINE_PROMPT = """Создай структуру (outline) для {content_type} на тему: {topic}

Исследованные факты:
{facts}

Верни структуру в виде:
# Заголовок
## Раздел 1
## Раздел 2
...
"""

_DRAFT_PROMPT = """Напиши {content_type} по следующей структуре.
Тема: {topic}
Стиль: {style}
Целевая аудитория: {audience}

Структура:
{outline}

Факты для включения:
{facts}

Требования: интересно, конкретно, без воды. Длина: {length}.
"""

_REVIEW_PROMPT = """Улучши следующий текст:
1. Исправь грамматику и стиль
2. Сделай более убедительным и ярким
3. Добавь призыв к действию если нужно
4. Убери воду и повторения

Текст:
{draft}

Верни только улучшенный текст без комментариев.
"""

CONTENT_TYPES = {
    "blog_post": {"length": "800-1200 слов", "style": "информационный, с примерами"},
    "social_post": {"length": "150-300 слов", "style": "вовлекающий, с хэштегами"},
    "summary": {"length": "200-400 слов", "style": "сжатый, структурированный"},
    "script": {"length": "500-1000 слов", "style": "разговорный, с паузами [...]"},
    "email": {"length": "100-300 слов", "style": "профессиональный, с призывом к действию"},
}


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


async def create_content(
    topic: str,
    content_type: str = "blog_post",
    audience: str = "широкая аудитория",
    research: bool = True,
    session_id: str = "content",
) -> dict[str, Any]:
    """
    Full content creation pipeline.

    Returns:
        {"topic": str, "content_type": str, "outline": str, "draft": str,
         "final": str, "facts_used": int, "nodes_created": int}
    """
    ct_config = CONTENT_TYPES.get(content_type, CONTENT_TYPES["blog_post"])
    facts: list[str] = []
    nodes_created = 0

    # Step 1: Research (optional)
    if research:
        try:
            from core.agents.researcher import research as do_research
            research_result = await do_research(topic, session_id=session_id)
            facts = research_result.get("facts", [])
            nodes_created = research_result.get("nodes_created", 0)
            logger.info("Research complete: %d facts for '%s'", len(facts), topic[:50])
        except Exception as exc:
            logger.warning("Research failed: %s", exc)

    facts_text = "\n".join(f"- {f}" for f in facts[:15]) or "Нет предварительных данных"

    # Step 2: Generate outline
    outline = await _call_kimi(
        _OUTLINE_PROMPT.format(
            content_type=content_type,
            topic=topic,
            facts=facts_text,
        )
    )

    # Step 3: Write draft
    draft = await _call_kimi(
        _DRAFT_PROMPT.format(
            content_type=content_type,
            topic=topic,
            style=ct_config["style"],
            audience=audience,
            outline=outline,
            facts=facts_text,
            length=ct_config["length"],
        )
    )

    # Step 4: Polish
    final = await _call_kimi(_REVIEW_PROMPT.format(draft=draft))

    return {
        "topic": topic,
        "content_type": content_type,
        "outline": outline,
        "draft": draft,
        "final": final,
        "facts_used": len(facts),
        "nodes_created": nodes_created,
        "session_id": session_id,
    }


async def generate_social_posts(
    topic: str,
    platforms: list[str] | None = None,
) -> dict[str, str]:
    """Generate platform-specific social media posts."""
    platforms = platforms or ["twitter", "linkedin", "telegram"]
    results: dict[str, str] = {}

    platform_prompts = {
        "twitter": f"Напиши Twitter-пост (до 280 символов) о: {topic}. Добавь 2-3 хэштега.",
        "linkedin": f"Напиши LinkedIn-пост (200-400 слов, профессиональный тон) о: {topic}.",
        "telegram": f"Напиши Telegram-пост (150-300 слов, с эмодзи) о: {topic}.",
        "instagram": f"Напиши Instagram-пост (100-200 слов) с хэштегами о: {topic}.",
    }

    for platform in platforms:
        prompt = platform_prompts.get(platform, f"Напиши пост для {platform} о: {topic}")
        try:
            results[platform] = await _call_kimi(prompt)
        except Exception as exc:
            results[platform] = f"[Ошибка генерации для {platform}: {exc}]"

    return results
