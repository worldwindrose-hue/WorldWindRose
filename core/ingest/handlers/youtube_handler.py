"""
ROSA OS — YouTube Handler.

Extracts subtitles (or transcribes via Whisper if none),
splits into chunks, saves to knowledge graph.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path
from typing import Any

from core.ingest.handlers.base import BaseHandler, IngestResult

logger = logging.getLogger("rosa.ingest.youtube")


class YouTubeHandler(BaseHandler):
    """Ingest YouTube videos and playlists."""

    async def process(self, job) -> IngestResult:
        url = job.source
        self.update_progress(job, 5, "Получаю информацию о видео...")

        try:
            return await self._process_url(job, url)
        except Exception as exc:
            logger.error("YouTube ingest failed: %s", exc)
            raise

    async def _process_url(self, job, url: str) -> IngestResult:
        import yt_dlp

        # Is it a playlist?
        if "playlist" in url or "list=" in url:
            return await self._process_playlist(job, url)

        info = self._extract_info(url)
        if not info:
            raise RuntimeError(f"Could not extract info from {url}")

        title = info.get("title", "Unknown")
        channel = info.get("uploader", "")
        description = info.get("description", "")
        tags = info.get("tags", []) or []
        duration = info.get("duration", 0)

        self.update_progress(job, 20, f"Видео: {title[:40]}")

        # Try subtitles first
        text = self._get_subtitles(info)
        method = "subtitles"

        if not text and duration and duration < 3600:
            # Try Whisper for videos under 1 hour
            text = await self._transcribe(job, url, title)
            method = "whisper"

        if not text:
            # Fall back to description only
            text = f"Title: {title}\nChannel: {channel}\n\n{description}"
            method = "metadata_only"

        self.update_progress(job, 80, "Сохраняю в граф знаний...")

        full_text = f"# {title}\n**Channel:** {channel}\n**URL:** {url}\n\n{text}"
        chunks = self.chunk(full_text)
        nodes = await self.save_to_graph(
            chunks,
            source=url,
            tags=["youtube"] + [t[:30] for t in tags[:5]],
            extra_meta={"title": title, "channel": channel, "method": method, "duration": duration},
        )

        self.update_progress(job, 100)
        return IngestResult(
            type="youtube",
            source=url,
            nodes_created=nodes,
            chunks=len(chunks),
            summary=f"✅ YouTube: «{title}» ({method}) → {nodes} узлов",
            metadata={"title": title, "channel": channel, "method": method},
        )

    async def _process_playlist(self, job, url: str) -> IngestResult:
        import yt_dlp
        total_nodes = 0
        total_chunks = 0
        opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        entries = info.get("entries", [])
        total = len(entries)
        for i, entry in enumerate(entries):
            self.update_progress(job, int((i / max(total, 1)) * 90), f"Видео {i+1}/{total}")
            try:
                video_url = entry.get("url") or f"https://youtube.com/watch?v={entry.get('id','')}"
                sub_job = type("J", (), {"id": job.id, "source": video_url})()
                r = await self._process_url(sub_job, video_url)
                total_nodes += r.nodes_created
                total_chunks += r.chunks
            except Exception as exc:
                logger.warning("Playlist video failed: %s", exc)

        return IngestResult(
            type="youtube",
            source=url,
            nodes_created=total_nodes,
            chunks=total_chunks,
            summary=f"✅ YouTube плейлист: {total} видео → {total_nodes} узлов",
        )

    def _extract_info(self, url: str) -> dict | None:
        import yt_dlp
        opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ru", "en"],
            "skip_download": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as exc:
            logger.warning("yt_dlp extract_info failed: %s", exc)
            return None

    def _get_subtitles(self, info: dict) -> str:
        """Extract subtitle text from yt-dlp info dict."""
        for lang in ("ru", "en", "en-orig"):
            subs = (info.get("subtitles") or {}).get(lang, [])
            if not subs:
                subs = (info.get("automatic_captions") or {}).get(lang, [])
            for sub in subs:
                if sub.get("ext") in ("vtt", "srv3", "json3"):
                    url = sub.get("url", "")
                    if url:
                        try:
                            import urllib.request
                            text = urllib.request.urlopen(url, timeout=15).read().decode("utf-8", errors="replace")
                            return self._clean_vtt(text)
                        except Exception:
                            pass
        return ""

    def _clean_vtt(self, vtt: str) -> str:
        """Strip VTT formatting tags and timestamps."""
        lines = vtt.splitlines()
        clean = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                continue
            line = re.sub(r"<[^>]+>", "", line)
            if line:
                clean.append(line)
        return " ".join(dict.fromkeys(clean))  # deduplicate consecutive lines

    async def _transcribe(self, job, url: str, title: str) -> str:
        """Download audio and transcribe with Whisper."""
        self.update_progress(job, 30, "Скачиваю аудио...")
        try:
            import whisper
            import yt_dlp
        except ImportError:
            logger.info("whisper/yt-dlp not available for transcription")
            return ""

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = str(Path(tmp) / "audio.mp3")
            opts = {
                "quiet": True,
                "format": "bestaudio/best",
                "outtmpl": audio_path.replace(".mp3", ""),
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
            except Exception as exc:
                logger.warning("Audio download failed: %s", exc)
                return ""

            # Find actual file (yt-dlp may append extension)
            files = list(Path(tmp).glob("*.mp3"))
            if not files:
                return ""

            self.update_progress(job, 55, "Транскрибирую...")
            try:
                model = whisper.load_model("small")
                result = model.transcribe(str(files[0]), language=None)
                return result.get("text", "")
            except Exception as exc:
                logger.warning("Whisper transcription failed: %s", exc)
                return ""
