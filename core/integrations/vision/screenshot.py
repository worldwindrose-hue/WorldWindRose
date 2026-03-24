"""
ROSA OS — Screenshot Capture (macOS).

Uses macOS `screencapture` CLI (no dependencies) for screen capture.
Returns base64-encoded PNG for sending to vision models.
"""

from __future__ import annotations

import base64
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.integrations.vision.screenshot")


def capture_screen(region: tuple[int, int, int, int] | None = None) -> dict[str, Any]:
    """
    Capture the entire screen (or a region) via macOS screencapture.

    Args:
        region: Optional (x, y, width, height) in pixels. macOS only.

    Returns:
        {"success": bool, "base64": str, "width": int, "height": int, "path": str}
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = ["screencapture", "-x", tmp_path]
        if region:
            x, y, w, h = region
            cmd = ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", tmp_path]

        proc = subprocess.run(cmd, capture_output=True, timeout=10)
        if proc.returncode != 0:
            return {
                "success": False,
                "error": proc.stderr.decode() or "screencapture failed",
                "base64": "",
            }

        img_bytes = Path(tmp_path).read_bytes()
        b64 = base64.b64encode(img_bytes).decode()

        # Try to get dimensions via PIL if available
        width = height = 0
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(img_bytes))
            width, height = img.size
        except Exception:
            pass

        return {
            "success": True,
            "base64": b64,
            "width": width,
            "height": height,
            "path": tmp_path,
            "size_bytes": len(img_bytes),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "screencapture timed out", "base64": ""}
    except Exception as exc:
        return {"success": False, "error": str(exc), "base64": ""}
    finally:
        # Keep temp file; caller decides cleanup
        pass


def capture_window(window_title: str | None = None) -> dict[str, Any]:
    """
    Capture a window by title using AppleScript + screencapture.
    Falls back to full screen if title is not found.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        if window_title:
            # Use screencapture -l with window ID via osascript
            script = f'tell application "{window_title}" to get id of window 1'
            osascript_proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5
            )
            window_id = osascript_proc.stdout.strip()
            if window_id.isdigit():
                cmd = ["screencapture", "-x", "-l", window_id, tmp_path]
            else:
                cmd = ["screencapture", "-x", tmp_path]
        else:
            cmd = ["screencapture", "-x", tmp_path]

        proc = subprocess.run(cmd, capture_output=True, timeout=10)
        if proc.returncode != 0:
            return {"success": False, "error": "screencapture failed", "base64": ""}

        img_bytes = Path(tmp_path).read_bytes()
        return {
            "success": True,
            "base64": base64.b64encode(img_bytes).decode(),
            "path": tmp_path,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc), "base64": ""}


async def analyze_screenshot(description_prompt: str = "Describe what you see on the screen.") -> dict[str, Any]:
    """
    Capture screen → send to vision-capable model → return description.
    """
    capture = capture_screen()
    if not capture["success"]:
        return {"success": False, "error": capture.get("error"), "description": ""}

    try:
        from openai import AsyncOpenAI
        from core.config import get_settings
        settings = get_settings()
        client = AsyncOpenAI(
            api_key=settings.openrouter_api_key,
            base_url="https://openrouter.ai/api/v1",
        )

        # Use a vision-capable model
        vision_model = getattr(settings, "vision_model", "google/gemini-flash-1.5")

        response = await client.chat.completions.create(
            model=vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": description_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{capture['base64']}"
                        },
                    },
                ],
            }],
            max_tokens=1024,
        )
        description = response.choices[0].message.content or ""
        return {"success": True, "description": description, "model": vision_model}

    except Exception as exc:
        logger.error("Screenshot analysis failed: %s", exc)
        return {"success": False, "error": str(exc), "description": ""}
