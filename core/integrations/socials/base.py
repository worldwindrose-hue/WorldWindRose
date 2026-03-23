"""
ROSA OS v3 — Base class for social/messaging connectors.
All connectors inherit from BaseSocialConnector.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseSocialConnector(ABC):
    """
    Abstract base for social network / messaging integrations.

    Subclasses must declare:
    - REQUIRED_ENV_VARS: list of env var names needed for this connector
    - SETUP_INSTRUCTIONS: human-readable setup guide (shown in Settings UI)
    """

    REQUIRED_ENV_VARS: list[str] = []
    SETUP_INSTRUCTIONS: str = "No setup instructions provided."

    @property
    def is_configured(self) -> bool:
        """Return True if all required env vars are set."""
        import os
        return all(os.getenv(var) for var in self.REQUIRED_ENV_VARS)

    @abstractmethod
    async def read(self, **kwargs) -> list[dict[str, Any]]:
        """Read messages/posts/data from the platform."""
        raise NotImplementedError

    @abstractmethod
    async def send(self, content: str, **kwargs) -> dict[str, Any]:
        """Send a message/post to the platform."""
        raise NotImplementedError

    async def analyze(self, items: list[dict[str, Any]], prompt: str = "") -> str:
        """
        Analyze fetched items using Rosa's LLM.
        Default implementation passes them to Kimi K2.5.
        """
        raise NotImplementedError("analyze() not implemented for this connector")
