from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Admin, Message, Payment, User


# ─── Users ────────────────────────────────────────────────────────────────────

async def get_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    language_code: Optional[str],
) -> tuple[User, bool]:
    user = await get_user(session, telegram_id)
    if user:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.last_active = datetime.utcnow()
        await session.commit()
        return user, False

    lang = _detect_language(language_code)
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language=lang,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True


def _detect_language(language_code: Optional[str]) -> str:
    if not language_code:
        return "ru"
    code = language_code.lower()
    if code.startswith("ru"):
        return "ru"
    if code.startswith("zh"):
        return "zh"
    if code.startswith("es"):
        return "es"
    if code.startswith("en"):
        return "en"
    return "ru"


async def update_user_language(session: AsyncSession, telegram_id: int, language: str):
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(language=language)
    )
    await session.commit()


async def block_user(session: AsyncSession, telegram_id: int, blocked: bool):
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(is_blocked=blocked)
    )
    await session.commit()


async def reset_user_limits(session: AsyncSession, telegram_id: int):
    """Обнуляет использованные бесплатные лимиты пользователя."""
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(
            free_messages_used=0,
            free_minutes_used=0.0,
        )
    )
    await session.commit()


async def set_user_unlimited(session: AsyncSession, telegram_id: int, unlimited: bool):
    """Включает или выключает безлимитный режим."""
    await session.execute(
        update(User).where(User.telegram_id == telegram_id).values(is_unlimited=unlimited)
    )
    await session.commit()


async def get_all_users(session: AsyncSession, offset: int = 0, limit: int = 10) -> list[User]:
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    return result.scalars().all()


async def count_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)))
    return result.scalar_one()


async def count_blocked_users(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(User.id)).where(User.is_blocked == True))
    return result.scalar_one()


# ─── Free tier check ──────────────────────────────────────────────────────────

def can_use_free(user: User, audio_duration_sec: float, free_messages_limit: int, free_minutes_limit: float) -> tuple[bool, str]:
    if user.free_messages_used >= free_messages_limit:
        return False, "msg_limit"
    duration_min = audio_duration_sec / 60
    if user.free_minutes_used + duration_min > free_minutes_limit:
        return False, "min_limit"
    return True, "ok"


# ─── Messages ─────────────────────────────────────────────────────────────────

async def save_message(
    session: AsyncSession,
    user_telegram_id: int,
    audio_duration: float,
    file_id: str,
    transcription: str,
    summary: str,
    recommendations: str,
    title: str,
    language: str,
    is_free: bool,
    is_unlimited: bool = False,
) -> Message:
    msg = Message(
        user_telegram_id=user_telegram_id,
        audio_duration=audio_duration,
        file_id=file_id,
        transcription=transcription,
        summary=summary,
        recommendations=recommendations,
        title=title,
        language=language,
        is_free=is_free,
    )
    session.add(msg)

    duration_min = audio_duration / 60
    update_vals: dict = {
        "total_messages": User.total_messages + 1,
        "total_minutes": User.total_minutes + duration_min,
        "last_active": datetime.utcnow(),
    }
    if is_unlimited:
        pass  # безлимит — только общую статистику обновляем
    elif is_free:
        update_vals["free_messages_used"] = User.free_messages_used + 1
        update_vals["free_minutes_used"] = User.free_minutes_used + duration_min
    else:
        update_vals["message_balance"] = User.message_balance - 1

    await session.execute(
        update(User).where(User.telegram_id == user_telegram_id).values(**update_vals)
    )
    await session.commit()
    await session.refresh(msg)
    return msg


async def get_user_messages(
    session: AsyncSession,
    telegram_id: int,
    offset: int = 0,
    limit: int = 8,
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.user_telegram_id == telegram_id)
        .order_by(Message.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


async def count_user_messages(session: AsyncSession, telegram_id: int) -> int:
    result = await session.execute(
        select(func.count(Message.id)).where(Message.user_telegram_id == telegram_id)
    )
    return result.scalar_one()


async def get_message_by_id(session: AsyncSession, message_id: int) -> Optional[Message]:
    result = await session.execute(select(Message).where(Message.id == message_id))
    return result.scalar_one_or_none()


async def get_all_user_messages(session: AsyncSession, telegram_id: int) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.user_telegram_id == telegram_id)
        .order_by(Message.created_at.asc())
    )
    return result.scalars().all()


async def count_total_messages(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(Message.id)))
    return result.scalar_one()


async def sum_total_minutes(session: AsyncSession) -> float:
    result = await session.execute(select(func.sum(Message.audio_duration)))
    val = result.scalar_one()
    return (val or 0.0) / 60


# ─── Payments ─────────────────────────────────────────────────────────────────

async def add_payment(
    session: AsyncSession,
    user_telegram_id: int,
    stars_amount: int,
    messages_purchased: int,
    payment_type: str,
    telegram_charge_id: str,
):
    payment = Payment(
        user_telegram_id=user_telegram_id,
        stars_amount=stars_amount,
        messages_purchased=messages_purchased,
        payment_type=payment_type,
        telegram_charge_id=telegram_charge_id,
    )
    session.add(payment)
    await session.execute(
        update(User)
        .where(User.telegram_id == user_telegram_id)
        .values(
            message_balance=User.message_balance + messages_purchased,
            total_stars_spent=User.total_stars_spent + stars_amount,
        )
    )
    await session.commit()


async def sum_total_stars(session: AsyncSession) -> int:
    result = await session.execute(select(func.sum(Payment.stars_amount)))
    return result.scalar_one() or 0


async def count_total_payments(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(Payment.id)))
    return result.scalar_one()


async def sum_stars_since(session: AsyncSession, since: datetime) -> int:
    result = await session.execute(
        select(func.sum(Payment.stars_amount)).where(Payment.created_at >= since)
    )
    return result.scalar_one() or 0


# ─── Admins ───────────────────────────────────────────────────────────────────

async def get_admin(session: AsyncSession, telegram_id: int) -> Optional[Admin]:
    result = await session.execute(
        select(Admin).where(Admin.user_telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def create_admin(session: AsyncSession, user_telegram_id: int, added_by: int) -> Admin:
    admin = Admin(user_telegram_id=user_telegram_id, added_by=added_by)
    session.add(admin)
    await session.commit()
    await session.refresh(admin)
    return admin


async def update_admin_permissions(session: AsyncSession, user_telegram_id: int, **permissions):
    await session.execute(
        update(Admin).where(Admin.user_telegram_id == user_telegram_id).values(**permissions)
    )
    await session.commit()


async def delete_admin(session: AsyncSession, user_telegram_id: int):
    admin = await get_admin(session, user_telegram_id)
    if admin:
        await session.delete(admin)
        await session.commit()


async def get_all_admins(session: AsyncSession) -> list[Admin]:
    result = await session.execute(select(Admin))
    return result.scalars().all()
