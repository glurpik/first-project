from aiogram import Router
from aiogram.types import ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION

import database as db

router = Router()


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_join(event: ChatMemberUpdated):
    """Tracks when a user joins a channel via invite link."""
    invite_link = event.invite_link
    if not invite_link:
        return

    link_record = await db.get_link_by_url(invite_link.invite_link)
    if not link_record:
        return

    joined_user_id = event.new_chat_member.user.id
    await db.record_join(link_record["id"], joined_user_id)
