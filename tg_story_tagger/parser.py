"""
Collects unique users from a Telegram chat or channel.
Saves results to a JSON file for use by the story tagger.
"""

import asyncio
import json
import logging
from pathlib import Path

from pyrogram import Client
from pyrogram.errors import FloodWait, ChatAdminRequired, PeerIdInvalid
from pyrogram.types import User

logger = logging.getLogger(__name__)


def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "first_name": u.first_name or "",
        "last_name": u.last_name or "",
    }


async def parse_members(
    client: Client,
    chat: str | int,
    limit: int = 5000,
) -> list[dict]:
    """Fetch chat members (works for supergroups, not broadcast channels)."""
    users = []
    try:
        async for member in client.get_chat_members(chat, limit=limit):
            if member.user and not member.user.is_bot and not member.user.is_deleted:
                users.append(_user_to_dict(member.user))
    except ChatAdminRequired:
        logger.warning("No admin rights to get members — falling back to message senders.")
        users = await parse_senders(client, chat, limit)
    except FloodWait as e:
        logger.warning("FloodWait %ds", e.value)
        await asyncio.sleep(e.value)
    return users


async def parse_senders(
    client: Client,
    chat: str | int,
    limit: int = 5000,
) -> list[dict]:
    """Collect unique senders from recent messages (works for channels too)."""
    seen: dict[int, dict] = {}
    try:
        async for msg in client.get_chat_history(chat, limit=limit):
            if msg.from_user and not msg.from_user.is_bot and not msg.from_user.is_deleted:
                u = msg.from_user
                seen[u.id] = _user_to_dict(u)
    except FloodWait as e:
        logger.warning("FloodWait %ds", e.value)
        await asyncio.sleep(e.value)
    except PeerIdInvalid:
        logger.error("Cannot access chat: %s", chat)
    return list(seen.values())


async def run_parser(
    session_path: str,
    api_id: int,
    api_hash: str,
    chat: str | int,
    output_file: str = "users.json",
    mode: str = "auto",  # "members" | "senders" | "auto"
    limit: int = 5000,
) -> list[dict]:
    async with Client(session_path, api_id=api_id, api_hash=api_hash) as client:
        logger.info("Parsing %s (mode=%s, limit=%d)...", chat, mode, limit)

        if mode == "members":
            users = await parse_members(client, chat, limit)
        elif mode == "senders":
            users = await parse_senders(client, chat, limit)
        else:
            users = await parse_members(client, chat, limit)
            if not users:
                users = await parse_senders(client, chat, limit)

    Path(output_file).write_text(json.dumps(users, ensure_ascii=False, indent=2))
    logger.info("Saved %d users to %s", len(users), output_file)
    return users
