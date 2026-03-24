"""
ROSA OS — GitHub Handler.

Reads public (and private with token) repos via GitHub REST API.
Extracts README + code files + repo metadata.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.ingest.handlers.base import BaseHandler, IngestResult

logger = logging.getLogger("rosa.ingest.github")

_CODE_EXTS = {".py", ".js", ".ts", ".go", ".rs", ".java", ".cpp", ".c", ".cs",
              ".rb", ".php", ".swift", ".kt", ".md", ".yaml", ".yml", ".json",
              ".toml", ".ini", ".sh", ".sql"}
_MAX_FILE_SIZE = 1_000_000  # 1MB per file


class GitHubHandler(BaseHandler):
    """Ingest GitHub repositories into the knowledge graph."""

    async def process(self, job) -> IngestResult:
        url = job.source
        self.update_progress(job, 5, "Анализирую репозиторий...")
        try:
            from core.integrations.workspace.github import GitHubConnector, parse_github_url
            owner, repo = parse_github_url(url)
            connector = GitHubConnector()

            self.update_progress(job, 20, f"Загружаю {owner}/{repo}...")
            result = await connector.ingest_to_graph(url, max_files=50)
            nodes = result.get("nodes_added", 0)
            files = result.get("files_processed", 0)

            self.update_progress(job, 100)
            return IngestResult(
                type="github",
                source=url,
                nodes_created=nodes,
                chunks=files,
                summary=f"✅ GitHub {owner}/{repo}: {files} файлов → {nodes} узлов",
                metadata={"owner": owner, "repo": repo, "files_processed": files},
            )
        except Exception as exc:
            logger.error("GitHub ingest failed: %s", exc)
            raise
