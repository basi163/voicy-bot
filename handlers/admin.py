import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import settings
from database.db import AsyncSessionLocal
from database.models import Admin, User
from database.repository import (
    block_user,
    count_blocked_users,
    count_total_messages,
    count_total_payments,
    count_users,
    create_admin,
    delete_admin,
    get_admin,
    get_all_admins,
    get_all_users,
    get_user,
    reset_user_limits,
    set_user_unlimited,
    sum_stars_since,
    sum_total_minutes,
    sum_total_stars,
    update_admin_permissions,
)
from services.i18n import lang_name, t

logger = logging.getLogger(__name__)
router = Router()

PAGE_SIZE = 8  # users per page


class AdminFSM(StatesGroup):
    waiting_for_user_id = State()


# ─── Access check helpers ─────────────────────────────────────────────────────

async def _get_admin_or_none(telegram_id: int) -> Optional[Admin]:
    async with AsyncSessionLocal() as session:
        return await get_admin(session, telegram_id)


def _is_super(telegram_id: int) -> bool:
    return telegram_id == settings.SUPER_ADMIN_ID


async def _has_access(telegram_id: int) -> bool:
    return _is_super(telegram_id) or await _get_admin_or_none(telegram_id) is not None


# ─── Admin menu keyboard ──────────────────────────────────────────────────────

def admin_menu_keyboard(lang: str, admin: Optional[Admin], is_super: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=t(lang, "admin_btn_stats"), callback_data="adm_stats")],
        [InlineKeyboardButton(text=t(lang, "admin_btn_users"), callback_data="adm_users_0")],
    ]
    can_finance = is_super or (admin and admin.can_view_finance)
    can_admins = is_super or (admin and admin.can_add_admins)

    if can_finance:
        buttons.append([InlineKeyboardButton(text=t(lang, "admin_btn_finance"), callback_data="adm_finance")])
    if can_admins:
        buttons.append([InlineKeyboardButton(text=t(lang, "admin_btn_admins"), callback_data="adm_admins")])

    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── /admin command ───────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, db_user: User, lang: str):
    if not await _has_access(db_user.telegram_id):
        await message.answer(t(lang, "admin_no_access"), parse_mode="HTML")
        return

    admin = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)

    await message.answer(
        t(lang, "admin_menu"),
        reply_markup=admin_menu_keyboard(lang, admin, is_super),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, db_user: User, lang: str):
    if not await _has_access(db_user.telegram_id):
        await callback.answer(t(lang, "admin_no_access"), show_alert=True)
        return

    admin = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)

    await callback.message.edit_text(
        t(lang, "admin_menu"),
        reply_markup=admin_menu_keyboard(lang, admin, is_super),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Global stats ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_stats")
async def cb_adm_stats(callback: CallbackQuery, db_user: User, lang: str):
    if not await _has_access(db_user.telegram_id):
        await callback.answer(t(lang, "admin_no_access"), show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        total_users = await count_users(session)
        blocked_users = await count_blocked_users(session)
        total_messages = await count_total_messages(session)
        total_minutes = await sum_total_minutes(session)

    text = t(
        lang, "admin_global_stats",
        total_users=total_users,
        blocked_users=blocked_users,
        total_messages=total_messages,
        total_minutes=total_minutes,
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="admin_menu")
    ]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ─── Finance stats ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_finance")
async def cb_adm_finance(callback: CallbackQuery, db_user: User, lang: str):
    admin = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin is None or not admin.can_view_finance):
        await callback.answer(t(lang, "admin_no_finance"), show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        total_stars = await sum_total_stars(session)
        total_payments = await count_total_payments(session)
        today_stars = await sum_stars_since(session, datetime.utcnow().replace(hour=0, minute=0, second=0))
        month_stars = await sum_stars_since(session, datetime.utcnow() - timedelta(days=30))

    text = t(
        lang, "admin_finance_stats",
        total_stars=total_stars,
        total_payments=total_payments,
        today_stars=today_stars,
        month_stars=month_stars,
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="admin_menu")
    ]])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


# ─── Users list ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_users_"))
async def cb_adm_users(callback: CallbackQuery, db_user: User, lang: str):
    if not await _has_access(db_user.telegram_id):
        await callback.answer(t(lang, "admin_no_access"), show_alert=True)
        return

    page = int(callback.data.split("_")[-1])
    offset = page * PAGE_SIZE

    async with AsyncSessionLocal() as session:
        total = await count_users(session)
        users = await get_all_users(session, offset=offset, limit=PAGE_SIZE)

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    buttons = []
    for u in users:
        name = u.first_name or u.username or str(u.telegram_id)
        status = "🚫" if u.is_blocked else "✅"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {name}",
            callback_data=f"adm_user_{u.telegram_id}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=t(lang, "admin_btn_prev"), callback_data=f"adm_users_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text=t(lang, "admin_btn_next"), callback_data=f"adm_users_{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="admin_menu")])

    text = t(lang, "admin_users_list", page=page + 1, total_pages=total_pages, total=total)
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Single user info ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_user_"))
async def cb_adm_user(callback: CallbackQuery, db_user: User, lang: str):
    if not await _has_access(db_user.telegram_id):
        await callback.answer(t(lang, "admin_no_access"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        target = await get_user(session, tid)
        target_admin = await get_admin(session, tid)

    if not target:
        await callback.answer("User not found", show_alert=True)
        return

    name = target.first_name or target.username or str(target.telegram_id)
    if target.is_blocked:
        status = t(lang, "admin_status_blocked")
    elif getattr(target, "is_unlimited", False):
        status = t(lang, "admin_status_unlimited")
    else:
        status = t(lang, "admin_status_active")

    text = t(
        lang, "admin_user_info",
        telegram_id=target.telegram_id,
        name=name,
        username=target.username or "—",
        language=lang_name(target.language),
        total_messages=target.total_messages,
        total_minutes=target.total_minutes,
        stars=target.total_stars_spent,
        balance=target.message_balance,
        free_used=target.free_messages_used,
        created_at=target.created_at.strftime("%Y-%m-%d"),
        status=status,
    )

    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    can_manage = is_super or (admin_obj and admin_obj.can_manage_users)
    can_add_adm = is_super or (admin_obj and admin_obj.can_add_admins)

    buttons = []
    if can_manage:
        if target.is_blocked:
            buttons.append([InlineKeyboardButton(
                text=t(lang, "admin_btn_unblock"),
                callback_data=f"adm_unblock_{tid}",
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text=t(lang, "admin_btn_block"),
                callback_data=f"adm_block_{tid}",
            )])
        # Reset limits button
        buttons.append([InlineKeyboardButton(
            text=t(lang, "admin_btn_reset_limits"),
            callback_data=f"adm_reset_{tid}",
        )])
        # Unlimited toggle
        is_unlimited = getattr(target, "is_unlimited", False)
        if is_unlimited:
            buttons.append([InlineKeyboardButton(
                text=t(lang, "admin_btn_remove_unlimited"),
                callback_data=f"adm_unlimited_off_{tid}",
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text=t(lang, "admin_btn_set_unlimited"),
                callback_data=f"adm_unlimited_on_{tid}",
            )])
    if can_add_adm and tid != db_user.telegram_id:
        if target_admin is not None:
            buttons.append([InlineKeyboardButton(
                text=t(lang, "admin_btn_remove_admin"),
                callback_data=f"adm_rmadmin_{tid}",
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text=t(lang, "admin_btn_make_admin"),
                callback_data=f"adm_mkadmin_{tid}",
            )])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="adm_users_0")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Block / Unblock ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_block_"))
async def cb_block(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_manage_users):
        await callback.answer(t(lang, "admin_no_manage_users"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await block_user(session, tid, True)

    await callback.answer(t(lang, "admin_user_blocked"), show_alert=True)
    # Refresh user info
    callback.data = f"adm_user_{tid}"
    await cb_adm_user(callback, db_user, lang)


@router.callback_query(F.data.startswith("adm_unblock_"))
async def cb_unblock(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_manage_users):
        await callback.answer(t(lang, "admin_no_manage_users"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await block_user(session, tid, False)

    await callback.answer(t(lang, "admin_user_unblocked"), show_alert=True)
    callback.data = f"adm_user_{tid}"
    await cb_adm_user(callback, db_user, lang)


# ─── Make / Remove admin ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_mkadmin_"))
async def cb_make_admin(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_add_admins):
        await callback.answer(t(lang, "admin_no_add_admins"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        target = await get_user(session, tid)
        existing = await get_admin(session, tid)
        if existing:
            await callback.answer(t(lang, "admin_already_admin"), show_alert=True)
            return
        await create_admin(session, tid, db_user.telegram_id)

    name = target.first_name or target.username or str(tid) if target else str(tid)
    await callback.answer(t(lang, "admin_added", name=name), show_alert=True)
    callback.data = f"adm_user_{tid}"
    await cb_adm_user(callback, db_user, lang)


@router.callback_query(F.data.startswith("adm_rmadmin_"))
async def cb_remove_admin(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_add_admins):
        await callback.answer(t(lang, "admin_no_add_admins"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        target = await get_user(session, tid)
        await delete_admin(session, tid)

    name = target.first_name or target.username or str(tid) if target else str(tid)
    await callback.answer(t(lang, "admin_removed", name=name), show_alert=True)
    callback.data = f"adm_user_{tid}"
    await cb_adm_user(callback, db_user, lang)


# ─── Admins list ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_admins")
async def cb_adm_admins(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_add_admins):
        await callback.answer(t(lang, "admin_no_add_admins"), show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        admins = await get_all_admins(session)
        admin_users = []
        for a in admins:
            u = await get_user(session, a.user_telegram_id)
            admin_users.append((a, u))

    buttons = []
    for a, u in admin_users:
        name = u.first_name or u.username or str(a.user_telegram_id) if u else str(a.user_telegram_id)
        buttons.append([InlineKeyboardButton(
            text=f"👑 {name}",
            callback_data=f"adm_perms_{a.user_telegram_id}",
        )])

    buttons.append([InlineKeyboardButton(
        text=t(lang, "admin_btn_add_admin"),
        callback_data="adm_add_admin",
    )])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="admin_menu")])

    await callback.message.edit_text(
        t(lang, "admin_admins_list"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Add admin by entering ID ─────────────────────────────────────────────────

@router.callback_query(F.data == "adm_add_admin")
async def cb_adm_add_admin(callback: CallbackQuery, db_user: User, lang: str, state: FSMContext):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_add_admins):
        await callback.answer(t(lang, "admin_no_add_admins"), show_alert=True)
        return

    await state.set_state(AdminFSM.waiting_for_user_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="adm_admins")
    ]])
    await callback.message.edit_text(t(lang, "admin_enter_id"), reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(StateFilter(AdminFSM.waiting_for_user_id))
async def handle_new_admin_id(message: Message, db_user: User, lang: str, state: FSMContext):
    await state.clear()
    try:
        tid = int(message.text.strip())
    except ValueError:
        await message.answer(t(lang, "admin_user_not_found"), parse_mode="HTML")
        return

    async with AsyncSessionLocal() as session:
        target = await get_user(session, tid)
        if not target:
            await message.answer(t(lang, "admin_user_not_found"), parse_mode="HTML")
            return
        existing = await get_admin(session, tid)
        if existing:
            await message.answer(t(lang, "admin_already_admin"), parse_mode="HTML")
            return
        await create_admin(session, tid, db_user.telegram_id)

    name = target.first_name or target.username or str(tid)
    await message.answer(t(lang, "admin_added", name=name), parse_mode="HTML")


# ─── Admin permissions ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_perms_"))
async def cb_adm_perms(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_manage_permissions):
        await callback.answer(t(lang, "admin_no_manage_perms"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])

    async with AsyncSessionLocal() as session:
        target_admin = await get_admin(session, tid)
        target_user = await get_user(session, tid)

    if not target_admin:
        await callback.answer("Admin not found", show_alert=True)
        return

    name = target_user.first_name or target_user.username or str(tid) if target_user else str(tid)

    def perm_btn(key: str, field: str, val: bool) -> InlineKeyboardButton:
        icon = t(lang, "admin_perm_on") if val else t(lang, "admin_perm_off")
        return InlineKeyboardButton(
            text=f"{icon} {t(lang, key)}",
            callback_data=f"adm_toggle_{tid}_{field}",
        )

    buttons = [
        [perm_btn("admin_perm_view_finance", "can_view_finance", target_admin.can_view_finance)],
        [perm_btn("admin_perm_manage_users", "can_manage_users", target_admin.can_manage_users)],
        [perm_btn("admin_perm_add_admins", "can_add_admins", target_admin.can_add_admins)],
        [perm_btn("admin_perm_manage_perms", "can_manage_permissions", target_admin.can_manage_permissions)],
        [InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="adm_admins")],
    ]

    await callback.message.edit_text(
        t(lang, "admin_permissions", name=name),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Reset user limits ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_reset_"))
async def cb_reset_limits(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_manage_users):
        await callback.answer(t(lang, "admin_no_manage_users"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await reset_user_limits(session, tid)

    await callback.answer(t(lang, "admin_reset_limits_ok"), show_alert=True)
    callback.data = f"adm_user_{tid}"
    await cb_adm_user(callback, db_user, lang)


# ─── Toggle unlimited mode ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm_unlimited_on_"))
async def cb_unlimited_on(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_manage_users):
        await callback.answer(t(lang, "admin_no_manage_users"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await set_user_unlimited(session, tid, True)

    await callback.answer(t(lang, "admin_unlimited_on"), show_alert=True)
    callback.data = f"adm_user_{tid}"
    await cb_adm_user(callback, db_user, lang)


@router.callback_query(F.data.startswith("adm_unlimited_off_"))
async def cb_unlimited_off(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_manage_users):
        await callback.answer(t(lang, "admin_no_manage_users"), show_alert=True)
        return

    tid = int(callback.data.split("_")[-1])
    async with AsyncSessionLocal() as session:
        await set_user_unlimited(session, tid, False)

    await callback.answer(t(lang, "admin_unlimited_off"), show_alert=True)
    callback.data = f"adm_user_{tid}"
    await cb_adm_user(callback, db_user, lang)


@router.callback_query(F.data.startswith("adm_toggle_"))
async def cb_adm_toggle_perm(callback: CallbackQuery, db_user: User, lang: str):
    admin_obj = await _get_admin_or_none(db_user.telegram_id)
    is_super = _is_super(db_user.telegram_id)
    if not is_super and (admin_obj is None or not admin_obj.can_manage_permissions):
        await callback.answer(t(lang, "admin_no_manage_perms"), show_alert=True)
        return

    parts = callback.data.split("_", 3)
    # adm_toggle_{tid}_{field}
    tid = int(parts[2])
    field = parts[3]

    valid_fields = {"can_view_finance", "can_manage_users", "can_add_admins", "can_manage_permissions"}
    if field not in valid_fields:
        await callback.answer()
        return

    async with AsyncSessionLocal() as session:
        target_admin = await get_admin(session, tid)
        if not target_admin:
            await callback.answer()
            return
        current_val = getattr(target_admin, field)
        await update_admin_permissions(session, tid, **{field: not current_val})

    await callback.answer(t(lang, "admin_permissions_saved"))
    callback.data = f"adm_perms_{tid}"
    await cb_adm_perms(callback, db_user, lang)
