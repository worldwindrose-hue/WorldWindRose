"""
ROSA OS — Archive Handler.

Unpacks ZIP/TAR archives to a temp dir and recursively ingests
each file via the universal_ingester.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from core.ingest.handlers.base import BaseHandler, IngestResult

logger = logging.getLogger("rosa.ingest.archive")

_BLOCKED_EXTS = {".exe", ".sh", ".bat", ".cmd", ".ps1", ".dll", ".so"}


class ArchiveHandler(BaseHandler):
    """Ingest ZIP/TAR archives by unpacking and recursively processing each file."""

    async def process(self, job) -> IngestResult:
        source = job.source
        self.update_progress(job, 5, "Распаковываю архив...")
        tmp_dir = Path(tempfile.mkdtemp(prefix="rosa_archive_"))
        try:
            self._extract(Path(source), tmp_dir)
            files = [p for p in tmp_dir.rglob("*") if p.is_file()]
            allowed = [f for f in files if f.suffix.lower() not in _BLOCKED_EXTS]
            blocked = len(files) - len(allowed)
            if blocked:
                logger.info("Blocked %d executable files in archive", blocked)

            self.update_progress(job, 20, f"Найдено {len(allowed)} файлов, начинаю поглощение...")

            total_nodes = 0
            total_chunks = 0
            from core.ingest.universal_ingester import ingest
            from core.ingest.job_queue import JobPriority
            sub_jobs = []
            for i, file_path in enumerate(allowed[:100]):  # cap at 100 files
                pct = 20 + int(70 * i / max(len(allowed), 1))
                self.update_progress(job, pct, f"Обрабатываю {file_path.name}...")
                sub_job = await ingest(
                    source=str(file_path),
                    priority=JobPriority.LOW,
                    metadata={"from_archive": source, "original_name": file_path.name},
                )
                sub_jobs.append(sub_job)

            # Wait for sub-jobs to complete (simple polling with timeout)
            import asyncio
            from core.ingest.job_queue import JobStatus
            deadline = 300  # 5 minutes max
            elapsed = 0
            while elapsed < deadline:
                done = sum(1 for j in sub_jobs if j.status in (JobStatus.DONE, JobStatus.FAILED))
                if done == len(sub_jobs):
                    break
                await asyncio.sleep(2)
                elapsed += 2

            for j in sub_jobs:
                if j.result:
                    total_nodes += j.result.get("nodes_created", 0)
                    total_chunks += j.result.get("chunks", 0)

            self.update_progress(job, 100)
            return IngestResult(
                type="archive",
                source=source,
                nodes_created=total_nodes,
                chunks=total_chunks,
                summary=f"✅ Архив: {len(allowed)} файлов → {total_chunks} чанков → {total_nodes} узлов",
                metadata={"files_found": len(files), "files_processed": len(allowed), "blocked": blocked},
            )
        except Exception as exc:
            logger.error("Archive ingest failed: %s", exc)
            raise
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _extract(self, path: Path, dest: Path) -> None:
        name = path.name.lower()
        if name.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(path) as zf:
                zf.extractall(dest)
        elif any(name.endswith(ext) for ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
            import tarfile
            with tarfile.open(path) as tf:
                tf.extractall(dest)
        else:
            raise ValueError(f"Unsupported archive format: {path.suffix}")
