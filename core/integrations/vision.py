"""
ROSA OS — Vision integration (Kimi-vision / GPT-4o vision).

Handles image analysis requests. When the cloud model supports vision
(e.g., moonshotai/kimi-vl or gpt-4o), this sends image data to the model.

Current status: CONDITIONAL — works if cloud model supports vision.
Falls back to stub message otherwise.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

logger = logging.getLogger("rosa.integrations.vision")

VISION_CAPABLE_MODELS = {
    "moonshotai/kimi-vl",
    "gpt-4o",
    "gpt-4-vision-preview",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-opus",
    "google/gemini-pro-vision",
    "google/gemini-1.5-pro",
}


class VisionClient:
    """
    Image analysis via vision-capable LLMs.

    Usage:
        client = VisionClient()
        description = await client.analyze_image("/path/to/image.jpg", "What is in this image?")
    """

    def __init__(self) -> None:
        from core.config import get_settings
        self.settings = get_settings()
        self.model = self.settings.cloud_model
        self.vision_available = self.model in VISION_CAPABLE_MODELS
        if not self.vision_available:
            logger.info(
                "VisionClient: model '%s' may not support vision. "
                "Set CLOUD_MODEL to a vision-capable model (e.g. moonshotai/kimi-vl).",
                self.model,
            )

    async def analyze_image(self, image_path: str, prompt: str = "Describe this image in detail.") -> str:
        """
        Analyze an image using the configured vision model.

        Args:
            image_path: Path to the image file
            prompt: What to ask about the image

        Returns:
            Text description/analysis from the model
        """
        path = Path(image_path)
        if not path.exists():
            return f"[Vision error: file not found: {image_path}]"

        # Encode image as base64
        try:
            image_data = path.read_bytes()
            b64 = base64.b64encode(image_data).decode()
            suffix = path.suffix.lower().lstrip(".")
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "gif": "image/gif", "webp": "image/webp"}.get(suffix, "image/png")
        except Exception as exc:
            return f"[Vision error: could not read image: {exc}]"

        if not self.settings.openrouter_api_key:
            return "[Vision: OPENROUTER_API_KEY not configured]"

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url=self.settings.openrouter_base_url,
                api_key=self.settings.openrouter_api_key,
            )
            response = await client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    ],
                }],
                max_tokens=1000,
            )
            return response.choices[0].message.content or "[Vision: no response]"
        except Exception as exc:
            logger.error("Vision analysis failed: %s", exc)
            return (
                f"[Vision analysis failed: {exc}. "
                f"To enable image analysis, set CLOUD_MODEL to a vision-capable model "
                f"such as 'moonshotai/kimi-vl' or 'gpt-4o' in your .env file.]"
            )
