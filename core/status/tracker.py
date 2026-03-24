"""
ROSA OS — Status Center.

Tracks Rosa's operational state in real-time.
Stores history in memory/status.db (separate aiosqlite DB).
Broadcasts updates to WebSocket subscribers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import uuid

logger = logging.getLogger("rosa.status")

_STATUS_DB = Path("memory/status.db")
_MAX_WS_SUBSCRIBERS = 100


class RosaStatus(str, Enum):
    ONLINE      = "ОНЛАЙН"       # Ready for dialog
    THINKING    = "ДУМАЕТ"       # Processing request
    ACTING      = "ДЕЙСТВУЕТ"    # Executing task/script
    SWARMING    = "СОВЕЩАЕТСЯ"   # Agent swarm running
    BROWSING    = "ПОСЕЩАЕТ"     # RPA browser open
    INFERRING   = "РЕШАЕТ"       # Active inference cycle
    UPDATING    = "ОБНОВЛЯЕТСЯ"  # Ouroboros patching
    OFFLINE     = "ОФЛАЙН"      # No internet, local mode
    STUCK       = "ЗАВИСЛА"     # Watchdog detected problem
    BROKEN      = "СЛОМАНА"     # Critical error, needs help


# Status → CSS color class
STATUS_COLOR: dict[RosaStatus, str] = {
    RosaStatus.ONLINE:    "green",
    RosaStatus.THINKING:  "green",
    RosaStatus.ACTING:    "green",
    RosaStatus.SWARMING:  "green",
    RosaStatus.BROWSING:  "green",
    RosaStatus.INFERRING: "green",
    RosaStatus.UPDATING:  "yellow",
    RosaStatus.OFFLINE:   "yellow",
    RosaStatus.STUCK:     "red",
    RosaStatus.BROKEN:    "red",
}


@dataclass
class StatusEvent:
    status: str                   # RosaStatus value
    detail: str = ""              # Human-readable detail
    url: str = ""                 # For BROWSING status
    agent_count: int = 0          # For SWARMING status
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: tuple) -> "StatusEvent":
        return cls(
            id=row[0],
            status=row[1],
            detail=row[2] or "",
            url=row[3] or "",
            agent_count=row[4] or 0,
            ts=row[5],
        )


class RosaStatusTracker:
    """Singleton tracker for Rosa's operational status."""

    def __init__(self) -> None:
        self._current: StatusEvent = StatusEvent(status=RosaStatus.ONLINE, detail="Готова к работе")
        self._subscribers: list[asyncio.Queue] = []
        self._db_ready = False
        self._lock = asyncio.Lock()

    async def _ensure_db(self) -> None:
        if self._db_ready:
            return
        try:
            import aiosqlite
            _STATUS_DB.parent.mkdir(parents=True, exist_ok=True)
            async with aiosqlite.connect(str(_STATUS_DB)) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS status_events (
                        id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        detail TEXT,
                        url TEXT,
                        agent_count INTEGER DEFAULT 0,
                        ts TEXT NOT NULL
                    )
                """)
                await db.commit()
            self._db_ready = True
        except Exception as exc:
            logger.debug("Status DB init failed (non-fatal): %s", exc)

    async def set_status(
        self,
        status: RosaStatus | str,
        detail: str = "",
        url: str = "",
        agents: int = 0,
    ) -> StatusEvent:
        """Update Rosa's current status and broadcast to subscribers."""
        if isinstance(status, RosaStatus):
            status_val = status.value
        else:
            status_val = status

        event = StatusEvent(
            status=status_val,
            detail=detail,
            url=url,
            agent_count=agents,
        )
        self._current = event

        # Persist to DB
        await self._ensure_db()
        try:
            import aiosqlite
            async with aiosqlite.connect(str(_STATUS_DB)) as db:
                await db.execute(
                    "INSERT INTO status_events (id, status, detail, url, agent_count, ts) VALUES (?, ?, ?, ?, ?, ?)",
                    (event.id, event.status, event.detail, event.url, event.agent_count, event.ts),
                )
                await db.commit()
        except Exception as exc:
            logger.debug("Status persist failed: %s", exc)

        # Broadcast to WebSocket subscribers
        payload = event.to_dict()
        dead = []
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self._subscribers.remove(q)

        logger.debug("Status → %s: %s", status_val, detail)
        return event

    def get_current(self) -> StatusEvent:
        return self._current

    async def get_history(self, limit: int = 50) -> list[StatusEvent]:
        await self._ensure_db()
        try:
            import aiosqlite
            async with aiosqlite.connect(str(_STATUS_DB)) as db:
                async with db.execute(
                    "SELECT id, status, detail, url, agent_count, ts FROM status_events ORDER BY ts DESC LIMIT ?",
                    (limit,),
                ) as cursor:
                    rows = await cursor.fetchall()
            return [StatusEvent.from_row(r) for r in rows]
        except Exception as exc:
            logger.debug("Status history failed: %s", exc)
            return [self._current]

    def subscribe(self) -> asyncio.Queue:
        """Return a new queue that receives status events."""
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass


# ── Module-level singleton ───────────────────────────────────────────────────

_tracker: RosaStatusTracker | None = None


def get_tracker() -> RosaStatusTracker:
    global _tracker
    if _tracker is None:
        _tracker = RosaStatusTracker()
    return _tracker


def set_status(
    status: RosaStatus | str,
    detail: str = "",
    url: str = "",
    agents: int = 0,
) -> None:
    """
    Fire-and-forget status update.
    Safe to call from sync code — creates asyncio.Task if loop is running.
    """
    tracker = get_tracker()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(tracker.set_status(status, detail, url, agents))
    except RuntimeError:
        # No running loop — update synchronously (tests, startup)
        tracker._current = StatusEvent(
            status=status.value if isinstance(status, RosaStatus) else status,
            detail=detail,
            url=url,
            agent_count=agents,
        )
