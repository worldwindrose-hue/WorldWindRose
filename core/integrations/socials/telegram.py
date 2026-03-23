"""
ROSA OS v3 — Telegram integration stub.

Required: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment.

Setup:
1. Create a bot via @BotFather on Telegram → get TELEGRAM_BOT_TOKEN
2. Add the bot to your chat/channel and get TELEGRAM_CHAT_ID
3. Add both to your .env file

TODO: Use python-telegram-bot or aiogram for production implementation.
"""

from __future__ import annotations

from typing import Any
from core.integrations.socials.base import BaseSocialConnector


class TelegramConnector(BaseSocialConnector):
    """Read and send messages via Telegram Bot API."""

    REQUIRED_ENV_VARS = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]

    SETUP_INSTRUCTIONS = """
    Настройка Telegram:
    1. Откройте @BotFather в Telegram
    2. Создайте нового бота командой /newbot
    3. Сохраните токен как TELEGRAM_BOT_TOKEN в .env
    4. Добавьте бота в нужный чат/канал
    5. Получите TELEGRAM_CHAT_ID (можно через @userinfobot)
    6. Добавьте TELEGRAM_CHAT_ID в .env
    Зависимость: pip install python-telegram-bot
    """

    async def read(self, limit: int = 20, **kwargs) -> list[dict[str, Any]]:
        """
        Read recent messages from the configured chat.
        TODO: Implement using Telegram Bot API getUpdates.
        """
        raise NotImplementedError(
            "TelegramConnector.read() — установите python-telegram-bot и задайте TELEGRAM_BOT_TOKEN"
        )

    async def send(self, content: str, chat_id: str | None = None, **kwargs) -> dict[str, Any]:
        """
        Send a message to the configured Telegram chat.
        TODO: Implement using Bot API sendMessage.
        """
        raise NotImplementedError(
            "TelegramConnector.send() — установите python-telegram-bot и задайте TELEGRAM_BOT_TOKEN"
        )

    async def analyze(self, items: list[dict[str, Any]], prompt: str = "") -> str:
        """Analyze fetched Telegram messages with Rosa's LLM."""
        raise NotImplementedError("TelegramConnector.analyze() — не реализовано")
