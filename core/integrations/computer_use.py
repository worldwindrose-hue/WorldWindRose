"""
ROSA OS — Perplexity Computer integration stub.

This module will be the bridge between ROSA Core and Perplexity Computer,
enabling Rosa to see the screen, click, type, and control macOS.

Current status: STUB — not yet connected.
When Perplexity Computer is available, implement the methods below.

Architecture hook:
  The RosaRouter in core/router.py will call ComputerUseClient.execute_action()
  when Rosa's plan requires interacting with the Mac desktop.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("rosa.integrations.computer_use")


class ComputerUseClient:
    """
    Perplexity Computer integration for macOS control.

    Future capabilities:
    - Screenshot capture and analysis
    - Mouse click/drag at coordinates
    - Keyboard input
    - Application launching
    - File system navigation via UI
    """

    def __init__(self) -> None:
        self.connected = False
        logger.info("ComputerUseClient initialized (stub mode — not yet connected)")

    async def screenshot(self) -> bytes | None:
        """Capture a screenshot. Returns PNG bytes or None if unavailable."""
        raise NotImplementedError(
            "Perplexity Computer is not yet connected. "
            "To enable: configure PERPLEXITY_COMPUTER_URL in .env once the integration is available."
        )

    async def execute_action(self, action: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a computer action.

        Expected action format:
        {
            "type": "click" | "type" | "scroll" | "key" | "screenshot",
            "coordinate": [x, y],     # for click/scroll
            "text": "...",            # for type/key
            "direction": "up"|"down", # for scroll
        }
        """
        raise NotImplementedError(
            "Perplexity Computer is not yet connected. "
            "This will enable Rosa to interact with your Mac desktop."
        )

    async def open_app(self, app_name: str) -> bool:
        """Open a macOS application by name."""
        raise NotImplementedError("Perplexity Computer not yet connected.")

    async def get_screen_context(self) -> str:
        """Return a description of what's currently on screen."""
        raise NotImplementedError("Perplexity Computer not yet connected.")
