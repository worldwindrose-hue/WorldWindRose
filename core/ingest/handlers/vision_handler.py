"""
ROSA OS — Vision Handler.

Describes images using Kimi Vision (via OpenRouter) or LLaVA locally.
Supports JPEG, PNG, GIF, WEBP, BMP.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from core.ingest.handlers.base import BaseHandler, IngestResult

logger = logging.getLogger("rosa.ingest.vision")

_VISION_MODEL = "moonshotai/moonshot-v1-8k"  # kimi vision
_VISION_PROMPT = (
    "Опиши это изображение подробно на русском языке. "
    "Включи: что изображено, текст на изображении (если есть), "
    "цвета, структуру, любые важные детали. "
    "Будь максимально информативен."
)
_MAX_SIZE_MB = 20


class VisionHandler(BaseHandler):
    """Describe images with Kimi Vision and save description to knowledge graph."""

    async def process(self, job) -> IngestResult:
        source = job.source
        self.update_progress(job, 5, "Загружаю изображение...")
        try:
            path = Path(source)
            size_mb = path.stat().st_size / 1_048_576
            if size_mb > _MAX_SIZE_MB:
                raise ValueError(f"Изображение слишком большое ({size_mb:.1f}MB > {_MAX_SIZE_MB}MB)")

            self.update_progress(job, 20, "Анализирую через Kimi Vision...")
            description = await self._describe(path)

            if not description.strip():
                raise ValueError("Не удалось получить описание изображения")

            self.update_progress(job, 70, "Сохраняю в граф знаний...")
            chunks = self.chunk(description)
            nodes = await self.save_to_graph(
                chunks,
                source=source,
                tags=["image", "vision"],
                extra_meta={"filename": path.name, "size_mb": round(size_mb, 2)},
            )

            self.update_progress(job, 100)
            return IngestResult(
                type="image",
                source=source,
                nodes_created=nodes,
                chunks=len(chunks),
                summary=f"✅ Изображение описано: {len(description)} символов → {nodes} узлов",
                metadata={"filename": path.name},
            )
        except Exception as exc:
            logger.error("Vision ingest failed: %s", exc)
            raise

    async def _describe(self, path: Path) -> str:
        # Try Kimi Vision via OpenRouter
        try:
            return await self._describe_kimi(path)
        except Exception as e:
            logger.warning("Kimi Vision failed: %s, trying LLaVA", e)
        # Try LLaVA local
        try:
            return await self._describe_llava(path)
        except Exception as e:
            logger.warning("LLaVA failed: %s", e)
            raise RuntimeError("Нет доступного vision-движка (Kimi или LLaVA)")

    async def _describe_kimi(self, path: Path) -> str:
        import httpx
        from core.config import get_settings
        settings = get_settings()
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")

        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        suffix = path.suffix.lower().lstrip(".")
        media_type = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png",
                      "gif": "gif", "webp": "webp", "bmp": "bmp"}.get(suffix, "jpeg")

        payload = {
            "model": _VISION_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/{media_type};base64,{img_b64}"}},
                    {"type": "text", "text": _VISION_PROMPT},
                ],
            }],
            "max_tokens": 1024,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                json=payload,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

    async def _describe_llava(self, path: Path) -> str:
        import httpx
        with open(path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "http://localhost:11434/api/generate",
                json={"model": "llava", "prompt": _VISION_PROMPT, "images": [img_b64], "stream": False},
            )
            r.raise_for_status()
            return r.json().get("response", "")
