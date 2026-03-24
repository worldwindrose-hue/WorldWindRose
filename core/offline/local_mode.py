"""
ROSA OS — Offline / Local Mode Manager (Phase 6).

Detects internet availability and switches Rosa to local models.
Queues messages when offline for later processing.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("rosa.offline")

_CHECK_INTERVAL = 60  # seconds
_is_online = True
_check_task: asyncio.Task | None = None
_running = False


async def check_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0) -> bool:
    """Check internet connectivity by attempting a TCP connection."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        return True
    except Exception:
        return False


async def get_online_status() -> bool:
    """Return cached internet status."""
    return _is_online


async def _check_loop() -> None:
    global _is_online, _running
    while _running:
        was_online = _is_online
        _is_online = await check_internet()

        if was_online and not _is_online:
            logger.warning("Internet lost — switching to offline mode")
            try:
                from core.status.tracker import set_status, RosaStatus
                set_status(RosaStatus.OFFLINE, "Нет интернета — работаю локально")
            except Exception:
                pass

        elif not was_online and _is_online:
            logger.info("Internet restored — switching back to online mode")
            try:
                from core.status.tracker import set_status, RosaStatus
                set_status(RosaStatus.ONLINE, "Интернет восстановлен")
                # Process queued messages
                from core.offline.message_queue import process_queue
                asyncio.create_task(process_queue())
            except Exception:
                pass

        await asyncio.sleep(_CHECK_INTERVAL)


def start_offline_monitor() -> None:
    global _check_task, _running
    if _running:
        return
    _running = True
    _check_task = asyncio.create_task(_check_loop())
    logger.info("Offline monitor started")


def stop_offline_monitor() -> None:
    global _check_task, _running
    _running = False
    if _check_task and not _check_task.done():
        _check_task.cancel()


def get_preferred_model() -> str:
    """Return preferred model based on connectivity."""
    if _is_online:
        try:
            from core.config import get_settings
            return get_settings().default_model
        except Exception:
            return "moonshotai/kimi-k2.5"
    else:
        # Offline: try Ollama local
        return "llama3.2"
