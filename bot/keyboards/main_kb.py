from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

LINKS_PER_PAGE = 7


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Мои ссылки", callback_data="my_links:1"))
    builder.row(InlineKeyboardButton(text="🏆 Таблица лидеров", callback_data="leaderboard"))
    return builder.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Мои ссылки", callback_data="my_links:1"))
    builder.row(InlineKeyboardButton(text="🏆 Таблица лидеров", callback_data="leaderboard"))
    builder.row(InlineKeyboardButton(text="⚙️ Панель админа", callback_data="admin_panel"))
    return builder.as_markup()


def admin_panel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👤 Выдать доступ", callback_data="admin_grant"))
    builder.row(InlineKeyboardButton(text="🚫 Забрать доступ", callback_data="admin_revoke"))
    builder.row(InlineKeyboardButton(text="📢 Добавить канал", callback_data="admin_add_channel"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить канал", callback_data="admin_remove_channel"))
    builder.row(InlineKeyboardButton(text="🔗 Создать ссылки юзеру", callback_data="admin_gen_links"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    return builder.as_markup()


def back_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    return builder.as_markup()


def links_pagination_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"my_links:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"my_links:{page + 1}"))
    builder.row(*nav_buttons)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    return builder.as_markup()


def leaderboard_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_main"))
    return builder.as_markup()


def channels_list_kb(channels: list[dict], action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        label = ch.get("title") or ch.get("username") or str(ch["channel_id"])
        builder.row(InlineKeyboardButton(
            text=label,
            callback_data=f"{action}:{ch['channel_id']}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    return builder.as_markup()
