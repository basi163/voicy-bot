import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

from faster_whisper import WhisperModel

from config import settings

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None
_executor = ThreadPoolExecutor(max_workers=2)

LANG_TO_WHISPER = {
    "ru": "ru",
    "en": "en",
    "zh": "zh",
    "es": "es",
}


def load_model():
    global _model
    logger.info(f"Loading Whisper model '{settings.WHISPER_MODEL}'...")
    _model = WhisperModel(
        settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
    )
    logger.info("Whisper model loaded.")


def _transcribe_sync(audio_path: str, language: str) -> tuple[str, float]:
    """Runs in a thread. Returns (transcription_text, duration_seconds)."""
    global _model
    if _model is None:
        load_model()

    whisper_lang = LANG_TO_WHISPER.get(language, language)
    segments, info = _model.transcribe(
        audio_path,
        language=whisper_lang,
        beam_size=5,
        vad_filter=True,
    )
    texts = [seg.text.strip() for seg in segments]
    transcription = " ".join(texts)
    duration = info.duration  # seconds
    return transcription, duration


async def transcribe(audio_path: str, language: str) -> tuple[str, float]:
    """Async wrapper. Returns (transcription_text, duration_seconds)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor, _transcribe_sync, audio_path, language
    )


async def save_audio_temp(audio_bytes: bytes, suffix: str = ".ogg") -> str:
    """Save audio bytes to a temp file, return path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(audio_bytes)
    except Exception:
        os.close(fd)
        raise
    return path
