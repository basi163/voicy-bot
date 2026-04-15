import io
import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import settings
from database.db import AsyncSessionLocal
from database.models import User
from database.repository import can_use_free, save_message
from handlers.payments import send_payment_offer
from services.deepseek_service import analyze
from services.i18n import t
from services.whisper_service import transcribe

logger = logging.getLogger(__name__)
router = Router()

SUPPORTED_MIME_TYPES = {
    "audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav",
    "audio/x-wav", "audio/flac", "audio/aac", "audio/m4a",
    "audio/x-m4a", "video/ogg",
}

MAX_TELEGRAM_DURATION = 59 * 60  # 59 минут в секундах


def result_keyboard(lang: str, msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "btn_transcript_file"), callback_data=f"tf_{msg_id}"),
            InlineKeyboardButton(text=t(lang, "btn_transcript_text"), callback_data=f"tt_{msg_id}"),
        ],
        [InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="main_menu")],
    ])


@router.message(F.voice)
async def handle_voice(message: Message, bot: Bot, db_user: User, lang: str):
    voice = message.voice
    await _process_audio(
        message=message, bot=bot, db_user=db_user, lang=lang,
        file_id=voice.file_id, duration=voice.duration, suffix=".ogg",
    )


@router.message(F.audio)
async def handle_audio(message: Message, bot: Bot, db_user: User, lang: str):
    audio = message.audio
    mime = audio.mime_type or ""
    if mime and mime not in SUPPORTED_MIME_TYPES and not mime.startswith("audio/"):
        await message.answer(t(lang, "unsupported_format"), parse_mode="HTML")
        return
    ext = _ext_from_mime(mime)
    await _process_audio(
        message=message, bot=bot, db_user=db_user, lang=lang,
        file_id=audio.file_id, duration=audio.duration or 0, suffix=ext,
    )


async def _process_audio(
    message: Message, bot: Bot, db_user: User, lang: str,
    file_id: str, duration: int, suffix: str,
):
    # ── Проверка баланса ──────────────────────────────────────────────────────
    if db_user.is_unlimited:
        # Безлимитный режим — проходим без списания
        is_free = False  # не считать как бесплатное, не тратить платный баланс
        _unlimited = True
    else:
        _unlimited = False
        can_free, reason = can_use_free(
            db_user, duration,
            settings.FREE_MESSAGES_LIMIT,
            settings.FREE_MINUTES_LIMIT,
        )
        has_paid = db_user.message_balance > 0

        if not can_free and not has_paid:
            key = "free_limit_reached" if reason in ("msg_limit", "min_limit") else "no_balance"
            await send_payment_offer(message, lang, key)
            return

        is_free = can_free

    # ── Обработка ─────────────────────────────────────────────────────────────
    status_msg = await message.answer(t(lang, "processing"), parse_mode="HTML")

    tmp_path = None
    try:
        file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(file.file_path)
        audio_data = file_bytes.read() if isinstance(file_bytes, io.BytesIO) else file_bytes

        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(audio_data)

        await status_msg.edit_text(t(lang, "transcribing"), parse_mode="HTML")
        transcription, actual_duration = await transcribe(tmp_path, lang)

        if not transcription.strip():
            await status_msg.edit_text(t(lang, "error_processing"), parse_mode="HTML")
            return

        await status_msg.edit_text(t(lang, "analyzing"), parse_mode="HTML")
        summary, recommendations, title = await analyze(transcription, lang)

        duration_min = actual_duration / 60

        async with AsyncSessionLocal() as session:
            msg = await save_message(
                session=session,
                user_telegram_id=db_user.telegram_id,
                audio_duration=actual_duration,
                file_id=file_id,
                transcription=transcription,
                summary=summary,
                recommendations=recommendations,
                title=title,
                language=lang,
                is_free=is_free,
                is_unlimited=_unlimited,
            )

        await status_msg.delete()
        await message.answer(
            t(lang, "result",
              summary=summary or "—",
              recommendations=recommendations or "—",
              duration=f"{duration_min:.1f}"),
            reply_markup=result_keyboard(lang, msg.id),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.exception(f"Error processing audio for user {db_user.telegram_id}: {e}")
        try:
            await status_msg.edit_text(t(lang, "error_processing"), parse_mode="HTML")
        except Exception:
            await message.answer(t(lang, "error_processing"), parse_mode="HTML")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _ext_from_mime(mime: str) -> str:
    mapping = {
        "audio/mpeg": ".mp3", "audio/ogg": ".ogg", "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a", "audio/m4a": ".m4a", "audio/wav": ".wav",
        "audio/x-wav": ".wav", "audio/flac": ".flac", "audio/aac": ".aac",
    }
    return mapping.get(mime, ".ogg")
