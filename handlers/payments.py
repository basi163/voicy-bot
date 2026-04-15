import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from config import settings
from database.db import AsyncSessionLocal
from database.models import User
from database.repository import add_payment
from services.i18n import t

logger = logging.getLogger(__name__)
router = Router()

PAYLOAD_1 = "buy_1_message"
PAYLOAD_BUNDLE = "buy_bundle_30"


PREMIUM_BOT_URL = "https://t.me/PremiumBot"


def payment_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "btn_buy_1"), callback_data="pay_1")],
        [InlineKeyboardButton(text=t(lang, "btn_buy_bundle"), callback_data="pay_bundle")],
        [InlineKeyboardButton(text=t(lang, "btn_buy_stars"), url=PREMIUM_BOT_URL)],
        [InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="main_menu")],
    ])


async def send_payment_offer(message: Message, lang: str, text_key: str = "no_balance"):
    await message.answer(
        t(lang, text_key),
        reply_markup=payment_keyboard(lang),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "buy")
async def cb_buy(callback: CallbackQuery, db_user: User, lang: str):
    await callback.message.edit_text(
        t(lang, "tariff_info", balance=db_user.message_balance, free_used=db_user.free_messages_used),
        reply_markup=payment_keyboard(lang),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "pay_1")
async def cb_pay_1(callback: CallbackQuery, lang: str):
    await callback.message.answer_invoice(
        title=t(lang, "invoice_1_title"),
        description=t(lang, "invoice_1_description"),
        payload=PAYLOAD_1,
        currency="XTR",
        prices=[LabeledPrice(label=t(lang, "invoice_1_title"), amount=settings.PER_MESSAGE_STARS)],
    )
    await callback.answer()


@router.callback_query(F.data == "pay_bundle")
async def cb_pay_bundle(callback: CallbackQuery, lang: str):
    await callback.message.answer_invoice(
        title=t(lang, "invoice_bundle_title"),
        description=t(lang, "invoice_bundle_description"),
        payload=PAYLOAD_BUNDLE,
        currency="XTR",
        prices=[LabeledPrice(label=t(lang, "invoice_bundle_title"), amount=settings.BUNDLE_STARS)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, db_user: User, lang: str):
    payment = message.successful_payment
    payload = payment.invoice_payload
    charge_id = payment.telegram_payment_charge_id

    if payload == PAYLOAD_1:
        stars = settings.PER_MESSAGE_STARS
        msgs = 1
        payment_type = "per_message"
    else:
        stars = settings.BUNDLE_STARS
        msgs = settings.BUNDLE_MESSAGES
        payment_type = "bundle"

    async with AsyncSessionLocal() as session:
        await add_payment(
            session=session,
            user_telegram_id=db_user.telegram_id,
            stars_amount=stars,
            messages_purchased=msgs,
            payment_type=payment_type,
            telegram_charge_id=charge_id,
        )

    new_balance = db_user.message_balance + msgs
    key = "payment_success_1" if payload == PAYLOAD_1 else "payment_success_bundle"
    await message.answer(
        t(lang, key, balance=new_balance),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "btn_menu"), callback_data="main_menu")],
        ]),
        parse_mode="HTML",
    )
