import math
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
from keyboards.main_kb import (
    main_menu_kb, admin_menu_kb, links_pagination_kb,
    leaderboard_kb, LINKS_PER_PAGE
)
from utils.texts import format_leaderboard, format_my_links, format_link_button
from config import ADMIN_IDS, MAX_SLOTS_PER_USER, leaderboard_last_updated, get_seconds_to_update

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def send_main_menu(target, user_id: int):
    kb = admin_menu_kb() if is_admin(user_id) else main_menu_kb()
    text = "👋 Привет! Выбери раздел:"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    else:
        await target.message.edit_text(text, reply_markup=kb)


@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.upsert_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.full_name or ""
    )
    user = await db.get_user(message.from_user.id)
    if not user or (not user["has_access"] and not is_admin(message.from_user.id)):
        await message.answer("❌ У тебя нет доступа. Обратись к администратору.")
        return
    await send_main_menu(message, message.from_user.id)


@router.callback_query(F.data == "back_main")
async def cb_back_main(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user or (not user["has_access"] and not is_admin(callback.from_user.id)):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await send_main_menu(callback, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("my_links:"))
async def cb_my_links(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user or (not user["has_access"] and not is_admin(callback.from_user.id)):
        await callback.answer("Нет доступа", show_alert=True)
        return

    page = int(callback.data.split(":")[1])
    links = await db.get_user_links(callback.from_user.id)
    total_slots = len(links)
    total_pages = max(1, math.ceil(total_slots / LINKS_PER_PAGE))
    page = max(1, min(page, total_pages))

    start = (page - 1) * LINKS_PER_PAGE
    page_links = links[start:start + LINKS_PER_PAGE]

    text = format_my_links(page_links, page, total_pages, total_slots, MAX_SLOTS_PER_USER)

    builder = InlineKeyboardBuilder()
    for link in page_links:
        btn_text = format_link_button(link)
        builder.row(InlineKeyboardButton(
            text=btn_text,
            url=link["invite_link"]
        ))

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"my_links:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"my_links:{page + 1}"))
    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "leaderboard")
async def cb_leaderboard(callback: CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    if not user or (not user["has_access"] and not is_admin(callback.from_user.id)):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await db.refresh_leaderboard()
    entries = await db.get_leaderboard()
    rank, user_joins = await db.get_user_rank(callback.from_user.id)
    seconds = get_seconds_to_update()

    text = format_leaderboard(entries, callback.from_user.id, rank, user_joins, seconds)
    await callback.message.edit_text(text, reply_markup=leaderboard_kb(), parse_mode="HTML")
    await callback.answer()
