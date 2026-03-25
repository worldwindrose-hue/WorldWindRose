"""ROSA OS — Knowledge Indexer. Auto-scans dirs, indexes new/changed files."""

from __future__ import annotations
import hashlib, json, logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("rosa.knowledge.indexer")
_INDEX_FILE = Path("memory/indexed_files.json")
_SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".claude"}
_MAX_FILE_MB = 50


def _file_hash(path: Path) -> str:
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def _load_index() -> dict:
    if _INDEX_FILE.exists():
        try:
            return json.loads(_INDEX_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_index(index: dict) -> None:
    _INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    _INDEX_FILE.write_text(json.dumps(index, indent=2))


class KnowledgeIndexer:
    def __init__(self, watch_dirs: list[str] = None):
        self._watch_dirs = watch_dirs or []
        self._index = _load_index()

    async def index_file(self, path: Path) -> int:
        """Index a single file. Returns chunks added (0 if skipped/error)."""
        path = Path(path)
        if not path.exists() or not path.is_file():
            return 0
        if path.stat().st_size > _MAX_FILE_MB * 1_048_576:
            logger.debug("Skipping large file: %s", path)
            return 0

        current_hash = _file_hash(path)
        key = str(path.resolve())
        if self._index.get(key) == current_hash:
            return 0  # already indexed

        try:
            from core.ingest.universal_ingester import ingest_text
            text = path.read_text(encoding="utf-8", errors="replace")
            if not text.strip():
                return 0
            result = await ingest_text(text, source=str(path), tags=["indexed", path.suffix.lstrip(".")])
            self._index[key] = current_hash
            _save_index(self._index)
            return result.chunks
        except Exception as exc:
            logger.debug("Index file error %s: %s", path, exc)
            return 0

    async def index_directory(self, dir_path: str, recursive: bool = True) -> dict:
        root = Path(dir_path)
        if not root.exists():
            return {"files": 0, "chunks": 0, "errors": 0}
        files = root.rglob("*") if recursive else root.glob("*")
        total_files = total_chunks = errors = 0
        for f in files:
            if f.is_file() and not any(p in _SKIP_DIRS for p in f.parts):
                try:
                    chunks = await self.index_file(f)
                    if chunks:
                        total_files += 1
                        total_chunks += chunks
                except Exception:
                    errors += 1
        return {"files": total_files, "chunks": total_chunks, "errors": errors}

    async def scan_and_index(self) -> dict:
        results = {}
        for d in self._watch_dirs:
            results[d] = await self.index_directory(d)
        return results

    def start_watchdog(self, dirs: list[str]) -> None:
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            import asyncio, threading

            class Handler(FileSystemEventHandler):
                def __init__(self, indexer):
                    self._indexer = indexer

                def on_modified(self, event):
                    if not event.is_directory:
                        try:
                            loop = asyncio.new_event_loop()
                            loop.run_until_complete(self._indexer.index_file(Path(event.src_path)))
                            loop.close()
                        except Exception:
                            pass

            observer = Observer()
            handler = Handler(self)
            for d in dirs:
                observer.schedule(handler, d, recursive=True)
            t = threading.Thread(target=observer.start, daemon=True)
            t.start()
            logger.info("Watchdog started for: %s", dirs)
        except ImportError:
            logger.debug("watchdog not installed — file watching disabled")


_indexer: Optional[KnowledgeIndexer] = None


def get_indexer(watch_dirs: list[str] = None) -> KnowledgeIndexer:
    global _indexer
    if _indexer is None:
        _indexer = KnowledgeIndexer(watch_dirs or [])
    return _indexer
