"""
ROSA OS v3 — Google Drive integration stub.

Required: GOOGLE_CREDENTIALS (path to credentials.json)

Setup:
1. Same Google Cloud project as Gmail (or create new)
2. Enable Google Drive API
3. Download/reuse credentials.json
4. Set GOOGLE_CREDENTIALS=/path/to/credentials.json in .env

TODO: Use google-api-python-client for production implementation.
"""

from __future__ import annotations

from typing import Any


class DriveConnector:
    """List, read, upload, and manage Google Drive files."""

    REQUIRED_ENV_VARS = ["GOOGLE_CREDENTIALS"]

    SETUP_INSTRUCTIONS = """
    Настройка Google Drive:
    1. Включите Google Drive API в https://console.cloud.google.com/
    2. Создайте OAuth2 credentials (или повторно используйте от Gmail)
    3. Задайте GOOGLE_CREDENTIALS=/путь/к/credentials.json в .env
    Зависимость: pip install google-api-python-client google-auth-oauthlib
    """

    @property
    def is_configured(self) -> bool:
        import os
        return bool(os.getenv("GOOGLE_CREDENTIALS"))

    async def list_files(
        self,
        query: str = "",
        mime_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List files in Google Drive, optionally filtered by query or MIME type."""
        raise NotImplementedError(
            "DriveConnector.list_files() — задайте GOOGLE_CREDENTIALS и установите google-api-python-client"
        )

    async def read_file(self, file_id: str) -> bytes:
        """Download a file's contents by its Drive ID."""
        raise NotImplementedError("DriveConnector.read_file() — не реализовано")

    async def upload_file(
        self,
        name: str,
        content: bytes,
        mime_type: str = "text/plain",
        folder_id: str | None = None,
    ) -> dict[str, Any]:
        """Upload a file to Google Drive."""
        raise NotImplementedError("DriveConnector.upload_file() — не реализовано")
