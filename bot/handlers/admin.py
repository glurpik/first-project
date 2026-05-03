from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards.main_kb import admin_panel_kb, cancel_kb, channels_list_kb
from config import ADMIN_IDS, MAX_SLOTS_PER_USER

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


class AdminStates(StatesGroup):
    waiting_grant_id = State()
    waiting_revoke_id = State()
    waiting_channel_id = State()
    waiting_remove_channel = State()
    waiting_gen_links_user = State()
    waiting_gen_links_channel = State()


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("⚙️ <b>Панель администратора</b>", reply_markup=admin_panel_kb(), parse_mode="HTML")
    await callback.answer()


# --- Grant access ---

@router.callback_query(F.data == "admin_grant")
async def cb_grant(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_grant_id)
    await callback.message.edit_text(
        "👤 Введи <b>user_id</b> или <b>@username</b> пользователя для выдачи доступа:",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_grant_id)
async def process_grant(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip().lstrip("@")
    try:
        user_id = int(text)
        user = await db.get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден в базе. Он должен сначала написать /start боту.", reply_markup=cancel_kb())
            return
        await db.grant_access(user_id)
        await message.answer(f"✅ Доступ выдан пользователю {user_id} ({user['username'] or user['full_name']})", reply_markup=admin_panel_kb())
    except ValueError:
        await message.answer("❌ Введи числовой user_id. Username-поиск пока не поддерживается.\nПопроси пользователя написать /start и узнай его ID.", reply_markup=cancel_kb())
        return
    await state.clear()


# --- Revoke access ---

@router.callback_query(F.data == "admin_revoke")
async def cb_revoke(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_revoke_id)
    await callback.message.edit_text(
        "🚫 Введи <b>user_id</b> пользователя для отзыва доступа:",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_revoke_id)
async def process_revoke(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовой user_id.", reply_markup=cancel_kb())
        return
    await db.revoke_access(user_id)
    await message.answer(f"✅ Доступ отозван у {user_id}", reply_markup=admin_panel_kb())
    await state.clear()


# --- Add channel ---

@router.callback_query(F.data == "admin_add_channel")
async def cb_add_channel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_channel_id)
    await callback.message.edit_text(
        "📢 Перешли любое сообщение из канала или введи <b>channel_id</b> (начинается с -100...).\n\n"
        "⚠️ Бот должен быть администратором в канале!",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_channel_id)
async def process_add_channel(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    channel_id = None
    if message.forward_from_chat:
        channel_id = message.forward_from_chat.id
        title = message.forward_from_chat.title or ""
        username = message.forward_from_chat.username or ""
    else:
        try:
            channel_id = int(message.text.strip())
            try:
                chat = await bot.get_chat(channel_id)
                title = chat.title or ""
                username = chat.username or ""
            except Exception:
                title = ""
                username = ""
        except ValueError:
            await message.answer("❌ Перешли сообщение из канала или введи числовой ID.", reply_markup=cancel_kb())
            return

    await db.add_channel(channel_id, title, username, message.from_user.id)
    await message.answer(f"✅ Канал добавлен: {title or channel_id}", reply_markup=admin_panel_kb())
    await state.clear()


# --- Remove channel ---

@router.callback_query(F.data == "admin_remove_channel")
async def cb_remove_channel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    channels = await db.get_channels()
    if not channels:
        await callback.answer("Нет добавленных каналов", show_alert=True)
        return
    await callback.message.edit_text(
        "🗑 Выбери канал для удаления:",
        reply_markup=channels_list_kb(channels, "del_ch")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("del_ch:"))
async def cb_do_remove_channel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    channel_id = int(callback.data.split(":")[1])
    await db.remove_channel(channel_id)
    await callback.message.edit_text("✅ Канал удалён.", reply_markup=admin_panel_kb())
    await callback.answer()


# --- Generate links for user ---

@router.callback_query(F.data == "admin_gen_links")
async def cb_gen_links(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return
    await state.set_state(AdminStates.waiting_gen_links_user)
    await callback.message.edit_text(
        "🔗 Введи <b>user_id</b> трафёра, которому нужно сгенерировать ссылки:",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_gen_links_user)
async def process_gen_links_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введи числовой user_id.", reply_markup=cancel_kb())
        return

    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден. Он должен сначала написать /start.", reply_markup=cancel_kb())
        return

    channels = await db.get_channels()
    if not channels:
        await message.answer("❌ Нет добавленных каналов. Сначала добавь каналы.", reply_markup=admin_panel_kb())
        await state.clear()
        return

    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminStates.waiting_gen_links_channel)
    await message.answer(
        f"📢 Выбери канал для генерации ссылки трафёру {user['username'] or user_id}:",
        reply_markup=channels_list_kb(channels, "gen_ch")
    )


@router.callback_query(F.data.startswith("gen_ch:"))
async def cb_do_gen_link(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer()
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    if not target_user_id:
        await callback.answer("Сессия устарела, начни заново.", show_alert=True)
        await state.clear()
        return

    channel_id = int(callback.data.split(":")[1])
    current_slots = await db.count_user_slots(target_user_id)

    if current_slots >= MAX_SLOTS_PER_USER:
        await callback.message.edit_text(
            f"❌ У трафёра уже максимум слотов ({MAX_SLOTS_PER_USER}).",
            reply_markup=admin_panel_kb()
        )
        await state.clear()
        await callback.answer()
        return

    try:
        user = await db.get_user(target_user_id)
        label = user["username"] or user["full_name"] or str(target_user_id)
        slot_number = await db.get_next_slot_number()
        link_obj = await bot.create_chat_invite_link(
            chat_id=channel_id,
            name=f"Slot #{slot_number} - {label}",
            creates_join_request=False
        )
        await db.save_invite_link(target_user_id, channel_id, link_obj.invite_link, slot_number, label)

        channel = await db.get_channel(channel_id)
        ch_name = channel["title"] or channel["username"] or str(channel_id)
        await callback.message.edit_text(
            f"✅ Ссылка создана для <b>{label}</b> в канале <b>{ch_name}</b>:\n"
            f"<code>{link_obj.invite_link}</code>\n"
            f"Слот: #{slot_number}",
            reply_markup=admin_panel_kb(), parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка создания ссылки: {e}\n\nПроверь, что бот — администратор канала.",
            reply_markup=admin_panel_kb()
        )

    await state.clear()
    await callback.answer()
