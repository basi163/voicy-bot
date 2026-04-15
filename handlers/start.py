from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import settings
from database.db import AsyncSessionLocal
from database.models import User
from database.repository import get_admin
from services.i18n import t

router = Router()


def main_menu_keyboard(lang: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=t(lang, "btn_stats"), callback_data="stats"),
            InlineKeyboardButton(text=t(lang, "btn_settings"), callback_data="settings"),
        ],
        [
            InlineKeyboardButton(text=t(lang, "btn_buy"), callback_data="buy"),
            InlineKeyboardButton(text=t(lang, "btn_transcriptions"), callback_data="transcriptions"),
        ],
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton(text=t(lang, "btn_admin"), callback_data="admin_menu"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def _send_menu(message: Message, db_user: User, lang: str):
    async with AsyncSessionLocal() as session:
        admin = await get_admin(session, db_user.telegram_id)
    is_admin = admin is not None or db_user.telegram_id == settings.SUPER_ADMIN_ID

    name = db_user.first_name or db_user.username or str(db_user.telegram_id)
    balance = db_user.message_balance

    if db_user.total_messages == 0 and db_user.free_messages_used == 0:
        text = t(lang, "welcome", name=name)
    else:
        text = t(lang, "welcome_back", name=name, balance=balance)

    await message.answer(
        text,
        reply_markup=main_menu_keyboard(lang, is_admin),
        parse_mode="HTML",
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, lang: str):
    await _send_menu(message, db_user, lang)


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: User, lang: str):
    await _send_menu(message, db_user, lang)


@router.message(Command("settings"))
async def cmd_settings_redirect(message: Message, db_user: User, lang: str):
    # Handled in settings.py — this ensures the command is registered
    from handlers.settings import cmd_settings
    await cmd_settings(message, db_user=db_user, lang=lang)


@router.message(Command("tariff"))
async def cmd_tariff(message: Message, db_user: User, lang: str):
    from handlers.payments import payment_keyboard
    text = t(
        lang, "tariff_info",
        balance=db_user.message_balance,
        free_used=db_user.free_messages_used,
    )
    from handlers.payments import PREMIUM_BOT_URL
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=t(lang, "btn_buy_1"), callback_data="pay_1"),
                InlineKeyboardButton(text=t(lang, "btn_buy_bundle"), callback_data="pay_bundle"),
            ],
            [InlineKeyboardButton(text=t(lang, "btn_buy_stars"), url=PREMIUM_BOT_URL)],
            [InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="main_menu")],
        ]),
        parse_mode="HTML",
    )


@router.message(Command("transcript"))
async def cmd_transcript_redirect(message: Message, db_user: User, lang: str):
    from handlers.stats import cmd_transcript
    await cmd_transcript(message, db_user=db_user, lang=lang)
