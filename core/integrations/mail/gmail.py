"""
ROSA OS v3 — Gmail integration stub.

Required: GMAIL_CREDENTIALS (path to credentials.json from Google OAuth2)
          or GMAIL_SERVICE_ACCOUNT_JSON (service account key JSON)

Setup:
1. Go to https://console.cloud.google.com/
2. Create a project → enable Gmail API
3. Create OAuth2 credentials → download credentials.json
4. Set GMAIL_CREDENTIALS=/path/to/credentials.json in .env
5. First run will open browser for OAuth flow → saves token.json

TODO: Use google-api-python-client for production implementation.
"""

from __future__ import annotations

from typing import Any


class GmailConnector:
    """Read, send, and label Gmail messages."""

    REQUIRED_ENV_VARS = ["GMAIL_CREDENTIALS"]

    SETUP_INSTRUCTIONS = """
    Настройка Gmail:
    1. Перейдите на https://console.cloud.google.com/
    2. Создайте проект → включите Gmail API
    3. Создайте учётные данные OAuth 2.0 → скачайте credentials.json
    4. Задайте GMAIL_CREDENTIALS=/путь/к/credentials.json в .env
    Зависимость: pip install google-api-python-client google-auth-oauthlib
    """

    @property
    def is_configured(self) -> bool:
        import os
        return bool(os.getenv("GMAIL_CREDENTIALS"))

    async def read(
        self,
        query: str = "",
        max_results: int = 20,
        label: str = "INBOX",
    ) -> list[dict[str, Any]]:
        """Read emails matching a query."""
        raise NotImplementedError(
            "GmailConnector.read() — задайте GMAIL_CREDENTIALS и установите google-api-python-client"
        )

    async def send(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
    ) -> dict[str, Any]:
        """Send an email."""
        raise NotImplementedError(
            "GmailConnector.send() — задайте GMAIL_CREDENTIALS и установите google-api-python-client"
        )

    async def label(self, message_id: str, label_name: str) -> dict[str, Any]:
        """Apply a label to a message."""
        raise NotImplementedError("GmailConnector.label() — не реализовано")
