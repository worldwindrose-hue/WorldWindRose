"""
ROSA OS v3 — Discord integration stub.

Required: DISCORD_TOKEN in environment.

Setup:
1. Create a Discord application at https://discord.com/developers/applications
2. Add a Bot user and copy the token as DISCORD_TOKEN
3. Invite the bot to your server with appropriate permissions
4. Add DISCORD_TOKEN to .env

TODO: Use discord.py or nextcord for production implementation.
"""

from __future__ import annotations

from typing import Any
from core.integrations.socials.base import BaseSocialConnector


class DiscordConnector(BaseSocialConnector):
    """Monitor channels and send messages via Discord Bot API."""

    REQUIRED_ENV_VARS = ["DISCORD_TOKEN"]

    SETUP_INSTRUCTIONS = """
    Настройка Discord:
    1. Перейдите на https://discord.com/developers/applications
    2. Создайте приложение → добавьте Bot
    3. Скопируйте токен как DISCORD_TOKEN в .env
    4. Пригласите бота на сервер с нужными правами
    Зависимость: pip install discord.py
    """

    async def read(self, channel_id: str | None = None, limit: int = 50, **kwargs) -> list[dict[str, Any]]:
        """Read messages from a Discord channel."""
        raise NotImplementedError(
            "DiscordConnector.read() — задайте DISCORD_TOKEN и установите discord.py"
        )

    async def send(self, content: str, channel_id: str | None = None, **kwargs) -> dict[str, Any]:
        """Send a message to a Discord channel."""
        raise NotImplementedError(
            "DiscordConnector.send() — задайте DISCORD_TOKEN и установите discord.py"
        )
