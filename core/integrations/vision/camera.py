"""
ROSA OS — Camera Stub (OpenCV).

Stub implementation for webcam capture.
Requires: pip install opencv-python
"""

from __future__ import annotations

import base64
import logging
from typing import Any

logger = logging.getLogger("rosa.integrations.vision.camera")


def is_available() -> bool:
    """Check if camera capture is available (OpenCV installed)."""
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def capture_frame(device_index: int = 0) -> dict[str, Any]:
    """
    Capture a single frame from the webcam.

    Returns:
        {"success": bool, "base64": str, "width": int, "height": int}
    """
    if not is_available():
        return {
            "success": False,
            "error": "OpenCV not installed. Run: pip install opencv-python",
            "base64": "",
        }

    try:
        import cv2
        import numpy as np

        cap = cv2.VideoCapture(device_index)
        if not cap.isOpened():
            return {"success": False, "error": f"Cannot open camera device {device_index}", "base64": ""}

        ret, frame = cap.read()
        cap.release()

        if not ret or frame is None:
            return {"success": False, "error": "Failed to capture frame", "base64": ""}

        height, width = frame.shape[:2]
        _, buffer = cv2.imencode(".png", frame)
        b64 = base64.b64encode(buffer.tobytes()).decode()

        return {
            "success": True,
            "base64": b64,
            "width": width,
            "height": height,
            "device_index": device_index,
        }
    except Exception as exc:
        logger.error("Camera capture failed: %s", exc)
        return {"success": False, "error": str(exc), "base64": ""}


def list_cameras() -> list[dict[str, Any]]:
    """List available camera devices."""
    if not is_available():
        return []

    cameras = []
    try:
        import cv2
        for i in range(5):  # Check first 5 device indices
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cameras.append({"index": i, "width": width, "height": height})
                cap.release()
    except Exception as exc:
        logger.debug("Camera enumeration failed: %s", exc)

    return cameras
