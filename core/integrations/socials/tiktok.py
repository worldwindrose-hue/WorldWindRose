"""
ROSA OS — TikTok Content Connector.
Extracts metadata from TikTok videos via yt-dlp (no download).
Hashtags, description, author → stored as KnowledgeNode metadata.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.integrations.socials.base import BaseSocialConnector

logger = logging.getLogger("rosa.integrations.tiktok")


class TikTokConnector(BaseSocialConnector):
    """Read TikTok video metadata without downloading the video."""

    REQUIRED_ENV_VARS = []  # public videos need no credentials
    SETUP_INSTRUCTIONS = """
TikTok — публичные видео не требуют авторизации.
Для приватного аккаунта можно добавить cookies:
  TIKTOK_COOKIES_FILE=/path/to/cookies.txt
Зависимость: yt-dlp (уже установлен)
"""

    async def read(self, url: str, **kwargs) -> list[dict[str, Any]]:
        """Extract metadata from a TikTok URL (video or profile)."""
        return await asyncio.get_event_loop().run_in_executor(None, self._extract_sync, url)

    def _extract_sync(self, url: str) -> list[dict[str, Any]]:
        try:
            import yt_dlp  # type: ignore
        except ImportError:
            raise RuntimeError("yt-dlp not installed. Run: pip install yt-dlp")

        import os
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        cookies_file = os.getenv("TIKTOK_COOKIES_FILE")
        if cookies_file:
            opts["cookiefile"] = cookies_file

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return []

        # Handle playlist (profile page) vs single video
        entries = info.get("entries") or [info]
        results = []
        for entry in entries[:20]:  # cap at 20 videos
            if not entry:
                continue
            tags = entry.get("tags") or []
            hashtags = [t for t in tags if t.startswith("#")] or tags[:10]
            results.append({
                "title": entry.get("title") or "",
                "description": entry.get("description") or "",
                "uploader": entry.get("uploader") or entry.get("channel") or "",
                "uploader_id": entry.get("uploader_id") or "",
                "hashtags": hashtags,
                "view_count": entry.get("view_count"),
                "like_count": entry.get("like_count"),
                "comment_count": entry.get("comment_count"),
                "upload_date": entry.get("upload_date") or "",
                "duration": entry.get("duration"),
                "webpage_url": entry.get("webpage_url") or url,
                "platform": "tiktok",
            })
        return results

    def _format_for_graph(self, items: list[dict]) -> str:
        """Convert metadata list into a text suitable for add_insight()."""
        parts = []
        for item in items:
            hashtag_str = " ".join(item.get("hashtags") or [])
            parts.append(
                f"TikTok от @{item['uploader']}: {item['title']}. "
                f"{item['description'][:300]} "
                f"Хэштеги: {hashtag_str} "
                f"Просмотры: {item.get('view_count')}, Лайки: {item.get('like_count')}."
            )
        return "\n\n".join(parts)

    async def send(self, content: str, **kwargs) -> dict[str, Any]:
        raise NotImplementedError("TikTok публикация не поддерживается через API")

    async def ingest_to_graph(self, url: str) -> dict[str, Any]:
        """Extract metadata + push to knowledge graph. Returns stats."""
        from core.knowledge.graph import add_insight

        items = await self.read(url)
        if not items:
            return {"nodes_created": 0, "edges_created": 0, "items_found": 0}

        text = self._format_for_graph(items)
        metadata = {
            "source_type": "tiktok",
            "url": url,
            "items": len(items),
        }
        result = await add_insight(text, metadata)
        result["items_found"] = len(items)
        result["sample_titles"] = [i["title"][:60] for i in items[:3]]
        return result
