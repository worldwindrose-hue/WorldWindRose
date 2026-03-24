"""
ROSA OS — Audio Handler.

Transcribes MP3/WAV/OGG/M4A/FLAC files using OpenAI Whisper (local).
Falls back to faster-whisper if available.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from core.ingest.handlers.base import BaseHandler, IngestResult

logger = logging.getLogger("rosa.ingest.audio")

_WHISPER_MODEL = "small"  # small/medium/large
_MAX_DURATION_HOURS = 2.0


class AudioHandler(BaseHandler):
    """Transcribe audio files and save to knowledge graph."""

    async def process(self, job) -> IngestResult:
        source = job.source
        self.update_progress(job, 5, "Подготавливаю аудио...")
        try:
            path = Path(source)
            duration = self._get_duration(path)
            if duration and duration > _MAX_DURATION_HOURS * 3600:
                raise ValueError(f"Аудио слишком длинное ({duration/3600:.1f}ч > {_MAX_DURATION_HOURS}ч)")

            self.update_progress(job, 10, "Запускаю Whisper (может занять время)...")
            transcript = await self._transcribe(path)

            if not transcript.strip():
                raise ValueError("Whisper не смог расшифровать аудио")

            self.update_progress(job, 70, "Сохраняю транскрипцию...")
            chunks = self.chunk(transcript)
            nodes = await self.save_to_graph(
                chunks,
                source=source,
                tags=["audio", "transcript"],
                extra_meta={"duration_sec": duration, "filename": path.name},
            )

            self.update_progress(job, 100)
            return IngestResult(
                type="audio",
                source=source,
                nodes_created=nodes,
                chunks=len(chunks),
                summary=f"✅ Аудио: {len(transcript)} символов → {nodes} узлов",
                metadata={"duration_sec": duration, "filename": path.name},
            )
        except Exception as exc:
            logger.error("Audio ingest failed: %s", exc)
            raise

    async def _transcribe(self, path: Path) -> str:
        # Try faster-whisper first (faster on CPU)
        try:
            return self._transcribe_faster_whisper(path)
        except ImportError:
            pass
        # Fall back to openai-whisper
        try:
            return self._transcribe_openai_whisper(path)
        except ImportError:
            raise ImportError(
                "Neither faster-whisper nor openai-whisper is installed. "
                "Run: pip install faster-whisper"
            )

    def _transcribe_faster_whisper(self, path: Path) -> str:
        from faster_whisper import WhisperModel
        model = WhisperModel(_WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path), beam_size=5, language=None)
        return " ".join(seg.text for seg in segments)

    def _transcribe_openai_whisper(self, path: Path) -> str:
        import whisper
        model = whisper.load_model(_WHISPER_MODEL)
        result = model.transcribe(str(path))
        return result["text"]

    def _get_duration(self, path: Path) -> float | None:
        try:
            import mutagen
            audio = mutagen.File(path)
            if audio and audio.info:
                return audio.info.length
        except Exception:
            pass
        try:
            import subprocess
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception:
            pass
        return None
