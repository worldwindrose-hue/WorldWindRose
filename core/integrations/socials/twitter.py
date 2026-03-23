"""
ROSA OS v3 — Twitter/X integration stub.

Required: TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN,
          TWITTER_ACCESS_SECRET in environment.

Setup:
1. Create a project/app at https://developer.twitter.com/
2. Generate API keys and access tokens
3. Add all four variables to .env

TODO: Use tweepy for production implementation.
"""

from __future__ import annotations

from typing import Any
from core.integrations.socials.base import BaseSocialConnector


class TwitterConnector(BaseSocialConnector):
    """Read and post tweets via Twitter API v2."""

    REQUIRED_ENV_VARS = [
        "TWITTER_API_KEY",
        "TWITTER_API_SECRET",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_SECRET",
    ]

    SETUP_INSTRUCTIONS = """
    Настройка Twitter/X:
    1. Зарегистрируйтесь на https://developer.twitter.com/
    2. Создайте проект и приложение
    3. Получите API Key, Secret, Access Token, Access Secret
    4. Добавьте все в .env
    Зависимость: pip install tweepy
    """

    async def read(self, query: str = "", limit: int = 20, **kwargs) -> list[dict[str, Any]]:
        """Search or read tweets."""
        raise NotImplementedError(
            "TwitterConnector.read() — задайте ключи Twitter API и установите tweepy"
        )

    async def send(self, content: str, **kwargs) -> dict[str, Any]:
        """Post a tweet."""
        raise NotImplementedError(
            "TwitterConnector.send() — задайте ключи Twitter API и установите tweepy"
        )
