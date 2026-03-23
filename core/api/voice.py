"""
ROSA OS v2 — Voice API
POST /api/voice/transcribe  — audio blob → text (Whisper via OpenAI direct key)
POST /api/voice/synthesize  — text → audio/mp3 (OpenAI TTS)

The browser-side Web Speech API is the primary STT/TTS mechanism (zero latency).
These endpoints are the backend fallback and are needed when:
  - Web Speech API is unavailable (Firefox, some mobile)
  - Higher-quality Whisper transcription is desired
  - Server-side TTS is needed

Both return 503 with a clear message if OPENAI_DIRECT_KEY is not configured.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger("rosa.api.voice")
router = APIRouter(prefix="/api/voice", tags=["voice"])


class TranscribeOut(BaseModel):
    text: str
    source: str   # "whisper" | "stub"


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "nova"   # OpenAI TTS voices: alloy, echo, fable, onyx, nova, shimmer


def _get_openai_client():
    from core.config import get_settings
    settings = get_settings()
    key = settings.openai_direct_key
    if not key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Voice API requires OPENAI_DIRECT_KEY in .env. "
                "Set it to your OpenAI API key (not OpenRouter). "
                "Alternatively, the browser Web Speech API works without any key."
            ),
        )
    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=key)


@router.post("/transcribe", response_model=TranscribeOut)
async def transcribe(audio: UploadFile = File(...)) -> TranscribeOut:
    """
    Transcribe audio to text using OpenAI Whisper.
    Accepts: audio/webm, audio/mp4, audio/wav, audio/ogg, audio/mpeg
    """
    client = _get_openai_client()

    content = await audio.read()
    filename = audio.filename or "audio.webm"
    content_type = audio.content_type or "audio/webm"

    try:
        # OpenAI expects a file-like object with a name attribute
        import io
        audio_file = io.BytesIO(content)
        audio_file.name = filename

        response = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
        return TranscribeOut(text=response.text, source="whisper")
    except Exception as exc:
        logger.error("Whisper transcription failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")


@router.post("/synthesize")
async def synthesize(body: SynthesizeRequest) -> Response:
    """
    Convert text to speech using OpenAI TTS.
    Returns audio/mpeg binary.
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    # Cap to avoid huge audio files
    text = body.text[:4000]

    client = _get_openai_client()

    try:
        response = await client.audio.speech.create(
            model="tts-1",
            voice=body.voice,
            input=text,
        )
        audio_bytes = response.content
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as exc:
        logger.error("TTS synthesis failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Speech synthesis failed: {exc}")
