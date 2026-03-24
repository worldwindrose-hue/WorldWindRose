"""
ROSA OS — Obsidian Vault Sync.

Bidirectional sync between ROSA knowledge graph and Obsidian vault (.md files).
- Import: reads .md files from vault → knowledge graph
- Export: writes knowledge nodes as .md files to vault
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("rosa.integrations.sync.obsidian")


def _get_vault_path() -> Path | None:
    """Get Obsidian vault path from env or default locations."""
    env_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    # Common macOS locations
    defaults = [
        Path.home() / "Documents" / "Obsidian",
        Path.home() / "Obsidian",
        Path.home() / "Documents" / "Notes",
    ]
    for p in defaults:
        if p.exists():
            return p
    return None


def parse_md_file(path: Path) -> dict[str, Any]:
    """Parse a markdown file into title + content + tags."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {"error": str(exc), "path": str(path)}

    # Extract frontmatter if present
    frontmatter: dict[str, Any] = {}
    content = text
    if text.startswith("---"):
        try:
            import yaml
            end = text.index("---", 3)
            fm_text = text[3:end]
            frontmatter = yaml.safe_load(fm_text) or {}
            content = text[end + 3:].strip()
        except Exception:
            pass

    # Extract tags from [[links]] and #tags
    links = re.findall(r"\[\[([^\]]+)\]\]", text)
    hashtags = re.findall(r"(?:^|\s)#(\w+)", text)
    tags = list(set(links + hashtags))

    return {
        "path": str(path),
        "name": path.stem,
        "title": frontmatter.get("title", path.stem),
        "content": content[:5000],  # cap at 5000 chars
        "tags": tags[:20],
        "frontmatter": frontmatter,
        "modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
    }


async def import_vault(
    vault_path: str | Path | None = None,
    max_files: int = 100,
    session_id: str = "obsidian",
) -> dict[str, Any]:
    """
    Import .md files from Obsidian vault into knowledge graph.

    Returns:
        {"files_scanned": int, "files_imported": int, "nodes_created": int}
    """
    vp = Path(vault_path) if vault_path else _get_vault_path()
    if not vp or not vp.exists():
        return {
            "error": "Obsidian vault not found. Set OBSIDIAN_VAULT_PATH env var.",
            "files_scanned": 0,
            "files_imported": 0,
            "nodes_created": 0,
        }

    try:
        from core.knowledge.graph import add_insight
    except ImportError:
        return {"error": "Knowledge graph not available", "nodes_created": 0}

    md_files = list(vp.rglob("*.md"))[:max_files]
    files_imported = 0
    nodes_created = 0

    for md_file in md_files:
        # Skip hidden files and Obsidian system files
        if any(part.startswith(".") for part in md_file.parts):
            continue

        parsed = parse_md_file(md_file)
        if "error" in parsed or not parsed.get("content", "").strip():
            continue

        text = f"{parsed['title']}\n\n{parsed['content']}"
        try:
            r = await add_insight(
                text=text,
                metadata={
                    "source": "obsidian",
                    "title": parsed["title"],
                    "tags": parsed["tags"],
                    "vault_path": str(vp),
                },
                session_id=session_id,
            )
            nodes_created += r.get("nodes_created", 0)
            files_imported += 1
        except Exception as exc:
            logger.debug("Obsidian import failed for %s: %s", md_file.name, exc)

    logger.info("Obsidian import: %d/%d files → %d nodes", files_imported, len(md_files), nodes_created)
    return {
        "vault_path": str(vp),
        "files_scanned": len(md_files),
        "files_imported": files_imported,
        "nodes_created": nodes_created,
    }


async def export_to_vault(
    vault_path: str | Path | None = None,
    session_id: str | None = None,
    max_nodes: int = 50,
) -> dict[str, Any]:
    """
    Export knowledge graph nodes to Obsidian vault as .md files.

    Returns:
        {"files_created": int, "vault_path": str}
    """
    vp = Path(vault_path) if vault_path else _get_vault_path()
    if not vp:
        return {"error": "No vault path configured", "files_created": 0}

    # Create ROSA export directory inside vault
    export_dir = vp / "ROSA_Export"
    export_dir.mkdir(exist_ok=True)

    try:
        from core.memory.store import get_store
        store = await get_store()
        nodes = await store.search_nodes(query="", limit=max_nodes)
    except Exception as exc:
        return {"error": str(exc), "files_created": 0}

    files_created = 0
    for node in nodes:
        try:
            node_id = getattr(node, "id", "unknown")
            title = getattr(node, "title", node_id)
            content = getattr(node, "content", "")
            source_type = getattr(node, "source_type", "rosa")
            created_at = getattr(node, "created_at", None)

            # Build frontmatter
            fm_lines = [
                "---",
                f"title: \"{title}\"",
                f"source: {source_type}",
                f"rosa_id: {node_id}",
            ]
            if created_at:
                fm_lines.append(f"created: {created_at.isoformat()}")
            fm_lines.append("---")
            fm = "\n".join(fm_lines)

            md_content = f"{fm}\n\n# {title}\n\n{content}\n"

            # Sanitize filename
            safe_name = re.sub(r"[^\w\s-]", "", title)[:60].strip()
            safe_name = re.sub(r"\s+", "_", safe_name)
            file_path = export_dir / f"{safe_name}.md"
            file_path.write_text(md_content, encoding="utf-8")
            files_created += 1
        except Exception as exc:
            logger.debug("Export node failed: %s", exc)

    logger.info("Obsidian export: %d files → %s", files_created, export_dir)
    return {
        "vault_path": str(vp),
        "export_dir": str(export_dir),
        "files_created": files_created,
    }
