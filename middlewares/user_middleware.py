from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from database.db import AsyncSessionLocal
from database.repository import get_or_create_user
from services.i18n import t


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            db_user, _ = await get_or_create_user(
                session=session,
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
            )

            if db_user.is_blocked:
                # Отправить сообщение о блокировке и прервать обработку
                from aiogram.types import Message, CallbackQuery
                lang = db_user.language
                if isinstance(event, (Message, CallbackQuery)):
                    if isinstance(event, Message):
                        await event.answer(t(lang, "user_blocked"))
                    else:
                        await event.answer(t(lang, "user_blocked"), show_alert=True)
                return

            data["db_user"] = db_user
            data["session"] = session
            data["lang"] = db_user.language

        return await handler(event, data)
