"""
ROSA OS — Federated Memory Stub.

Placeholder for future cross-device memory federation.
Currently: local JSON-based memory exchange.

Future plans:
- End-to-end encrypted sync via Cloudflare Workers
- Conflict resolution via vector clocks
- Privacy-preserving aggregation (differential privacy)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.memory.federated")

_SYNC_DIR = Path.home() / ".rosa_federated"


class FederatedMemory:
    """
    Stub federated memory implementation.
    Uses local filesystem for now.
    """

    def __init__(self, node_id: str = "local") -> None:
        self.node_id = node_id
        self._sync_dir = _SYNC_DIR / node_id
        self._sync_dir.mkdir(parents=True, exist_ok=True)

    async def push(self, key: str, value: Any) -> dict[str, Any]:
        """Push a memory entry to the federated store."""
        entry = {
            "key": key,
            "value": value,
            "node_id": self.node_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": 1,
        }
        file_path = self._sync_dir / f"{key}.json"

        # Increment version if exists
        if file_path.exists():
            try:
                existing = json.loads(file_path.read_text())
                entry["version"] = existing.get("version", 0) + 1
            except Exception:
                pass

        file_path.write_text(json.dumps(entry, ensure_ascii=False, indent=2))
        logger.debug("Federated push: %s (v%d)", key, entry["version"])
        return {"success": True, "key": key, "version": entry["version"]}

    async def pull(self, key: str) -> Any | None:
        """Pull a memory entry from the federated store."""
        file_path = self._sync_dir / f"{key}.json"
        if not file_path.exists():
            return None
        try:
            entry = json.loads(file_path.read_text())
            return entry.get("value")
        except Exception as exc:
            logger.warning("Federated pull failed for %s: %s", key, exc)
            return None

    async def sync(self, remote_dir: str | Path | None = None) -> dict[str, Any]:
        """
        Sync with another node (local path for now).
        Future: sync with remote URL.
        """
        if remote_dir is None:
            return {"synced": 0, "note": "No remote configured — local only mode"}

        remote_path = Path(remote_dir)
        if not remote_path.exists():
            return {"synced": 0, "error": f"Remote path not found: {remote_dir}"}

        synced = 0
        conflicts = 0

        for local_file in self._sync_dir.glob("*.json"):
            remote_file = remote_path / local_file.name
            try:
                local_data = json.loads(local_file.read_text())
                if remote_file.exists():
                    remote_data = json.loads(remote_file.read_text())
                    # Last-write-wins conflict resolution
                    if local_data.get("timestamp", "") >= remote_data.get("timestamp", ""):
                        remote_file.write_text(local_file.read_text())
                        synced += 1
                    else:
                        # Remote is newer — pull it
                        local_file.write_text(remote_file.read_text())
                        synced += 1
                        conflicts += 1
                else:
                    remote_file.write_text(local_file.read_text())
                    synced += 1
            except Exception as exc:
                logger.debug("Sync failed for %s: %s", local_file.name, exc)

        return {
            "synced": synced,
            "conflicts_resolved": conflicts,
            "node_id": self.node_id,
            "remote_dir": str(remote_dir),
        }

    def list_keys(self) -> list[str]:
        """List all stored keys."""
        return [f.stem for f in self._sync_dir.glob("*.json")]

    def stats(self) -> dict[str, Any]:
        keys = self.list_keys()
        return {
            "node_id": self.node_id,
            "keys_stored": len(keys),
            "sync_dir": str(self._sync_dir),
            "status": "stub_local_only",
        }


# Singleton
_federated: FederatedMemory | None = None


def get_federated_memory() -> FederatedMemory:
    global _federated
    if _federated is None:
        _federated = FederatedMemory()
    return _federated
