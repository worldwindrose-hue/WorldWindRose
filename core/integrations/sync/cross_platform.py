"""
ROSA OS — Cross-Platform Sync.

Syncs ROSA knowledge and settings across:
- Local filesystem (JSON export/import)
- Clipboard (quick share)
- Future: iCloud / Google Drive stubs
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.integrations.sync.cross_platform")

_DEFAULT_EXPORT_DIR = Path.home() / ".rosa_sync"


async def export_knowledge(
    output_path: str | Path | None = None,
    session_id: str | None = None,
    max_nodes: int = 500,
) -> dict[str, Any]:
    """
    Export all knowledge nodes to a JSON file for cross-device sync.

    Returns:
        {"success": bool, "path": str, "nodes_exported": int}
    """
    output_dir = Path(output_path) if output_path else _DEFAULT_EXPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"rosa_knowledge_{timestamp}.json"

    try:
        from core.memory.store import get_store
        store = await get_store()
        nodes = await store.search_nodes(query="", limit=max_nodes)
    except Exception as exc:
        return {"success": False, "error": str(exc), "nodes_exported": 0}

    export_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": "4.0",
        "nodes": [
            {
                "id": getattr(n, "id", ""),
                "title": getattr(n, "title", ""),
                "content": getattr(n, "content", ""),
                "type": getattr(n, "type", "insight"),
                "source_type": getattr(n, "source_type", ""),
                "tags": getattr(n, "tags", ""),
                "created_at": getattr(n, "created_at", None) and n.created_at.isoformat(),
            }
            for n in nodes
        ],
    }

    output_file.write_text(json.dumps(export_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Exported %d nodes to %s", len(nodes), output_file)

    return {
        "success": True,
        "path": str(output_file),
        "nodes_exported": len(nodes),
    }


async def import_knowledge(
    input_path: str | Path,
    session_id: str = "import",
) -> dict[str, Any]:
    """
    Import knowledge nodes from a JSON export file.

    Returns:
        {"success": bool, "nodes_imported": int, "nodes_skipped": int}
    """
    input_file = Path(input_path)
    if not input_file.exists():
        return {"success": False, "error": f"File not found: {input_file}", "nodes_imported": 0}

    try:
        data = json.loads(input_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"success": False, "error": f"JSON parse error: {exc}", "nodes_imported": 0}

    nodes = data.get("nodes", [])
    imported = skipped = 0

    try:
        from core.knowledge.graph import add_insight
    except ImportError:
        return {"success": False, "error": "Knowledge graph not available", "nodes_imported": 0}

    for node in nodes:
        content = node.get("content", "")
        title = node.get("title", "")
        if not content.strip():
            skipped += 1
            continue

        try:
            text = f"{title}\n\n{content}" if title else content
            await add_insight(
                text=text,
                metadata={"source": "cross_platform_import", "original_id": node.get("id")},
                session_id=session_id,
            )
            imported += 1
        except Exception as exc:
            logger.debug("Node import failed: %s", exc)
            skipped += 1

    logger.info("Cross-platform import: %d imported, %d skipped", imported, skipped)
    return {
        "success": True,
        "nodes_imported": imported,
        "nodes_skipped": skipped,
        "source_version": data.get("version", "unknown"),
    }


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard (macOS)."""
    import subprocess
    try:
        proc = subprocess.run(
            ["pbcopy"],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=5,
        )
        return proc.returncode == 0
    except Exception as exc:
        logger.debug("Clipboard copy failed: %s", exc)
        return False


def read_from_clipboard() -> str:
    """Read text from system clipboard (macOS)."""
    import subprocess
    try:
        proc = subprocess.run(
            ["pbpaste"],
            capture_output=True,
            timeout=5,
        )
        return proc.stdout.decode("utf-8", errors="replace")
    except Exception:
        return ""
