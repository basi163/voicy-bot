import math
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import settings
from database.db import AsyncSessionLocal
from database.models import User
from database.repository import (
    count_user_messages,
    get_admin,
    get_all_user_messages,
    get_message_by_id,
    get_user_messages,
)
from services.i18n import lang_name, t

router = Router()

PAGE_SIZE = 8


# ─── Helpers ──────────────────────────────────────────────────────────────────

def menu_btn(lang: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="main_menu")


def back_to_list_btn(lang: str, page: int = 0) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t(lang, "btn_to_list"), callback_data=f"transcriptions_p_{page}")


# ─── Statistics ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery, db_user: User, lang: str):
    free_minutes_left = max(0.0, settings.FREE_MINUTES_LIMIT - db_user.free_minutes_used)
    text = t(
        lang, "stats",
        total_messages=db_user.total_messages,
        total_minutes=db_user.total_minutes,
        total_stars=db_user.total_stars_spent,
        free_used=db_user.free_messages_used,
        free_minutes_left=free_minutes_left,
        balance=db_user.message_balance,
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[menu_btn(lang)]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ─── Main menu callback ───────────────────────────────────────────────────────

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, db_user: User, lang: str):
    from handlers.start import main_menu_keyboard
    async with AsyncSessionLocal() as session:
        admin = await get_admin(session, db_user.telegram_id)
    is_admin = admin is not None or db_user.telegram_id == settings.SUPER_ADMIN_ID

    await callback.message.edit_text(
        t(lang, "main_menu", balance=db_user.message_balance),
        reply_markup=main_menu_keyboard(lang, is_admin),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Transcriptions list ──────────────────────────────────────────────────────

@router.message(Command("transcript"))
async def cmd_transcript(message: Message, db_user: User, lang: str):
    await _show_transcriptions_list(message, db_user, lang, page=0, edit=False)


@router.callback_query(F.data == "transcriptions")
async def cb_transcriptions(callback: CallbackQuery, db_user: User, lang: str):
    await _show_transcriptions_list(callback.message, db_user, lang, page=0, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("transcriptions_p_"))
async def cb_transcriptions_page(callback: CallbackQuery, db_user: User, lang: str):
    page = int(callback.data.split("_")[-1])
    await _show_transcriptions_list(callback.message, db_user, lang, page=page, edit=True)
    await callback.answer()


async def _show_transcriptions_list(
    message: Message, db_user: User, lang: str, page: int, edit: bool
):
    async with AsyncSessionLocal() as session:
        total = await count_user_messages(session, db_user.telegram_id)
        msgs = await get_user_messages(session, db_user.telegram_id, offset=page * PAGE_SIZE, limit=PAGE_SIZE)

    if total == 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[[menu_btn(lang)]])
        text = t(lang, "transcriptions_empty")
        if edit:
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    buttons = []
    for msg in msgs:
        dt = msg.created_at.strftime("%d.%m.%y %H:%M")
        title = msg.title or "—"
        label = f"{dt} | {title}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"transcript_{msg.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=t(lang, "admin_btn_prev"), callback_data=f"transcriptions_p_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text=t(lang, "admin_btn_next"), callback_data=f"transcriptions_p_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([menu_btn(lang)])

    text = t(lang, "transcriptions_list", page=page + 1, total_pages=total_pages, total=total)
    if edit:
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


# ─── Single transcription detail ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("transcript_") & ~F.data.startswith("transcript_p_"))
async def cb_transcript_detail(callback: CallbackQuery, db_user: User, lang: str):
    # Handles transcript_{id}  (not transcript_p_ which is pagination)
    parts = callback.data.split("_")
    try:
        msg_id = int(parts[-1])
    except ValueError:
        await callback.answer()
        return

    async with AsyncSessionLocal() as session:
        msg = await get_message_by_id(session, msg_id)

    if not msg or msg.user_telegram_id != db_user.telegram_id:
        await callback.answer("Not found", show_alert=True)
        return

    dt = msg.created_at.strftime("%d.%m.%y %H:%M")
    duration_min = msg.audio_duration / 60
    title = msg.title or "—"

    text = t(
        lang, "transcript_detail",
        title=title,
        date=dt,
        duration=f"{duration_min:.1f}",
        language=lang_name(msg.language),
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t(lang, "btn_dl_file"), callback_data=f"tf_{msg_id}"),
            InlineKeyboardButton(text=t(lang, "btn_dl_text"), callback_data=f"tt_{msg_id}"),
        ],
        [back_to_list_btn(lang), menu_btn(lang)],
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ─── Transcript as file ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tf_"))
async def cb_transcript_file(callback: CallbackQuery, db_user: User, lang: str):
    msg_id = int(callback.data.split("_")[1])

    async with AsyncSessionLocal() as session:
        msg = await get_message_by_id(session, msg_id)

    if not msg or msg.user_telegram_id != db_user.telegram_id:
        await callback.answer("Not found", show_alert=True)
        return

    dt = msg.created_at.strftime("%d.%m.%y %H:%M")
    duration_min = msg.audio_duration / 60
    title = msg.title or "recording"

    lines = [
        f"TRANSCRIPTION",
        f"Date: {dt}",
        f"Title: {title}",
        f"Duration: {duration_min:.1f} min",
        f"Language: {msg.language}",
        "=" * 50,
        "",
        msg.transcription or "",
        "",
        "=" * 50,
        "SUMMARY:",
        msg.summary or "",
        "",
        "RECOMMENDATIONS:",
        msg.recommendations or "",
    ]
    content = "\n".join(lines).encode("utf-8")
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:30].strip()
    filename = f"{msg.created_at.strftime('%Y%m%d_%H%M')}_{safe_title}.txt"

    await callback.message.answer_document(
        BufferedInputFile(content, filename=filename),
        caption=t(lang, "transcript_file_caption", title=title, date=dt),
    )
    await callback.answer()


# ─── Transcript as text ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tt_"))
async def cb_transcript_text(callback: CallbackQuery, db_user: User, lang: str):
    msg_id = int(callback.data.split("_")[1])

    async with AsyncSessionLocal() as session:
        msg = await get_message_by_id(session, msg_id)

    if not msg or msg.user_telegram_id != db_user.telegram_id:
        await callback.answer("Not found", show_alert=True)
        return

    dt = msg.created_at.strftime("%d.%m.%y %H:%M")
    duration_min = msg.audio_duration / 60
    transcription = msg.transcription or ""

    header = t(lang, "transcript_text_intro", date=dt, duration=f"{duration_min:.1f}")
    full_text = f"{header}\n\n{transcription}"

    # Split into 4000-char chunks
    chunk_size = 4000
    chunks = [full_text[i:i + chunk_size] for i in range(0, len(full_text), chunk_size)]

    for chunk in chunks:
        await callback.message.answer(chunk, parse_mode="HTML")

    await callback.answer()
