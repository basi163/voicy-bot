from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database.db import AsyncSessionLocal
from database.models import User
from database.repository import update_user_language
from services.i18n import lang_name, t

router = Router()


def settings_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_lang"), callback_data="language_menu")],
        [InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="main_menu")],
    ])


def language_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_lang_ru"), callback_data="setlang_ru")],
        [InlineKeyboardButton(text=t(lang, "btn_lang_en"), callback_data="setlang_en")],
        [InlineKeyboardButton(text=t(lang, "btn_lang_zh"), callback_data="setlang_zh")],
        [InlineKeyboardButton(text=t(lang, "btn_lang_es"), callback_data="setlang_es")],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="settings")],
        [InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="main_menu")],
    ])


@router.message(Command("settings"))
async def cmd_settings(message: Message, db_user: User, lang: str):
    await message.answer(
        t(lang, "settings", lang_name=lang_name(lang)),
        reply_markup=settings_keyboard(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery, db_user: User, lang: str):
    await callback.message.edit_text(
        t(lang, "settings", lang_name=lang_name(lang)),
        reply_markup=settings_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "language_menu")
async def cb_language_menu(callback: CallbackQuery, db_user: User, lang: str):
    await callback.message.edit_text(
        t(lang, "language_select"),
        reply_markup=language_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setlang_"))
async def cb_set_language(callback: CallbackQuery, db_user: User, lang: str):
    new_lang = callback.data.split("_", 1)[1]
    if new_lang not in ("ru", "en", "zh", "es"):
        await callback.answer()
        return

    async with AsyncSessionLocal() as session:
        await update_user_language(session, db_user.telegram_id, new_lang)

    await callback.message.edit_text(
        t(new_lang, "language_changed", lang_name=lang_name(new_lang)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(new_lang, "btn_menu"), callback_data="main_menu")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()
