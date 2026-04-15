import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import settings
from database.db import init_db
from handlers import admin, payments, settings as settings_handler, start, stats, voice
from middlewares.user_middleware import UserMiddleware
from services.i18n import load_translations
from services.whisper_service import load_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Commands per language
COMMANDS = {
    "ru": [
        BotCommand(command="menu",       description="Главное меню"),
        BotCommand(command="settings",   description="Настройки языка"),
        BotCommand(command="transcript", description="Мои записи и транскрипции"),
        BotCommand(command="tariff",     description="Тарифы и пополнение баланса"),
    ],
    "en": [
        BotCommand(command="menu",       description="Main menu"),
        BotCommand(command="settings",   description="Language settings"),
        BotCommand(command="transcript", description="My recordings and transcriptions"),
        BotCommand(command="tariff",     description="Pricing and top up balance"),
    ],
    "zh": [
        BotCommand(command="menu",       description="主菜单"),
        BotCommand(command="settings",   description="语言设置"),
        BotCommand(command="transcript", description="我的录音和转录"),
        BotCommand(command="tariff",     description="价格和充值"),
    ],
    "es": [
        BotCommand(command="menu",       description="Menú principal"),
        BotCommand(command="settings",   description="Configuración de idioma"),
        BotCommand(command="transcript", description="Mis grabaciones y transcripciones"),
        BotCommand(command="tariff",     description="Precios y recargar saldo"),
    ],
}


async def register_commands(bot: Bot):
    for lang_code, commands in COMMANDS.items():
        await bot.set_my_commands(commands, language_code=lang_code)
    # Default (fallback) — English
    await bot.set_my_commands(COMMANDS["en"])
    logger.info("Bot commands registered.")


async def on_startup(bot: Bot):
    logger.info("Initialising database...")
    os.makedirs("data", exist_ok=True)
    await init_db()

    logger.info("Loading translations...")
    load_translations()

    logger.info("Loading Whisper model...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, load_model)

    await register_commands(bot)
    logger.info("Bot started.")


async def main():
    if not settings.BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set in .env")
    if not settings.DEEPSEEK_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY is not set in .env")
    if not settings.SUPER_ADMIN_ID:
        raise ValueError("SUPER_ADMIN_ID is not set in .env")

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(UserMiddleware())

    dp.include_router(start.router)
    dp.include_router(voice.router)
    dp.include_router(payments.router)
    dp.include_router(stats.router)
    dp.include_router(settings_handler.router)
    dp.include_router(admin.router)

    await on_startup(bot)

    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
