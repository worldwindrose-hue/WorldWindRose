"""
ROSA OS — Memory Backup Manager (Phase 3).

Auto-backup of Rosa's DB to memory/backups/.
Keeps last 30 backups. Restores on demand.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.memory.backup")

_BACKUP_DIR = Path("memory/backups")
_DB_PATH = Path("memory/rosa.db")
_MAX_BACKUPS = 30
_BACKUP_INTERVAL_HOURS = 1

_backup_task: asyncio.Task | None = None
_running = False


def _backup_name() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"rosa_backup_{ts}.db"


async def create_backup() -> dict[str, Any]:
    """Create a backup of rosa.db."""
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not _DB_PATH.exists():
        return {"success": False, "error": "Database not found"}
    dest = _BACKUP_DIR / _backup_name()
    shutil.copy2(str(_DB_PATH), str(dest))
    size = dest.stat().st_size
    logger.info("Backup created: %s (%d bytes)", dest.name, size)

    # Prune old backups
    _prune_old_backups()

    return {"success": True, "path": str(dest), "size": size}


def _prune_old_backups() -> None:
    backups = sorted(_BACKUP_DIR.glob("rosa_backup_*.db"), key=lambda p: p.stat().st_mtime)
    while len(backups) > _MAX_BACKUPS:
        old = backups.pop(0)
        old.unlink(missing_ok=True)
        logger.info("Pruned old backup: %s", old.name)


def list_backups() -> list[dict[str, Any]]:
    """List available backups, newest first."""
    if not _BACKUP_DIR.exists():
        return []
    backups = sorted(
        _BACKUP_DIR.glob("rosa_backup_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [
        {
            "name": p.name,
            "path": str(p),
            "size": p.stat().st_size,
            "modified": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(),
        }
        for p in backups
    ]


async def restore_backup(backup_path: str) -> dict[str, Any]:
    """Restore database from a backup file."""
    src = Path(backup_path)
    if not src.exists():
        return {"success": False, "error": f"Backup not found: {src}"}

    # Save current DB before replacing
    if _DB_PATH.exists():
        emergency = _BACKUP_DIR / f"pre_restore_{_backup_name()}"
        _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_DB_PATH), str(emergency))
        logger.info("Pre-restore backup saved: %s", emergency.name)

    shutil.copy2(str(src), str(_DB_PATH))

    # Reset store singleton so new DB is used
    try:
        from core.memory import store as store_module
        store_module._store = None
    except Exception:
        pass

    logger.info("Restored DB from %s", src.name)
    return {"success": True, "restored_from": str(src)}


async def _backup_loop() -> None:
    global _running
    while _running:
        await asyncio.sleep(_BACKUP_INTERVAL_HOURS * 3600)
        if _running:
            try:
                await create_backup()
            except Exception as exc:
                logger.error("Auto-backup failed: %s", exc)


def start_backup_scheduler() -> None:
    global _backup_task, _running
    if _running:
        return
    _running = True
    _backup_task = asyncio.create_task(_backup_loop())
    logger.info("Backup scheduler started (every %dh)", _BACKUP_INTERVAL_HOURS)


def stop_backup_scheduler() -> None:
    global _backup_task, _running
    _running = False
    if _backup_task and not _backup_task.done():
        _backup_task.cancel()
    _backup_task = None
