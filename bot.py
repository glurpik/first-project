"""
Telegram bot: parses chat history and tags all unique commenters.

Commands (admin only):
  /tag        — scan history of current chat and mention everyone
  /tag N      — scan last N messages (default 100, max 500)
  /tag_clear  — clear saved users list for this chat

Setup:
  1. pip install -r requirements.txt
  2. Copy .env.example to .env and fill in BOT_TOKEN
  3. Add the bot to your group/channel as admin with "Read messages" permission
  4. python bot.py
"""

import asyncio
import logging
import os
from collections import defaultdict

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]

# chat_id -> {user_id: mention_text}
seen_users: dict[int, dict[int, str]] = defaultdict(dict)


def build_mention(user) -> str:
    """Return inline mention or @username."""
    if user.username:
        return f"@{user.username}"
    name = user.full_name or str(user.id)
    return f'<a href="tg://user?id={user.id}">{name}</a>'


async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    member = await context.bot.get_chat_member(chat_id, user_id)
    return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track every message sender in memory."""
    msg = update.effective_message
    if not msg or not msg.from_user:
        return
    user = msg.from_user
    if user.is_bot:
        return
    chat_id = update.effective_chat.id
    seen_users[chat_id][user.id] = build_mention(user)


async def cmd_tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /tag [N]
    Scans last N messages from Telegram history (requires bot to be admin),
    merges with in-memory tracked users, then posts one message tagging all.
    """
    if not await is_admin(update, context):
        await update.message.reply_text("Только администраторы могут использовать /tag.")
        return

    chat_id = update.effective_chat.id

    limit = 100
    if context.args:
        try:
            limit = max(1, min(int(context.args[0]), 500))
        except ValueError:
            await update.message.reply_text("Использование: /tag [количество сообщений, макс 500]")
            return

    status_msg = await update.message.reply_text(
        f"Сканирую последние {limit} сообщений..."
    )

    # Fetch history via getChatHistory (works in supergroups/channels)
    try:
        async for msg in context.bot.get_chat_history(chat_id, limit=limit):
            if msg.from_user and not msg.from_user.is_bot:
                u = msg.from_user
                seen_users[chat_id][u.id] = build_mention(u)
    except Exception as exc:
        logger.warning("get_chat_history failed (%s), using only tracked users.", exc)

    users = seen_users.get(chat_id, {})
    if not users:
        await status_msg.edit_text("Не нашёл ни одного участника в истории.")
        return

    # Split into chunks ≤30 mentions to avoid message length limits
    mentions = list(users.values())
    chunk_size = 30
    chunks = [mentions[i : i + chunk_size] for i in range(0, len(mentions), chunk_size)]

    await status_msg.delete()

    for idx, chunk in enumerate(chunks):
        header = "Участники чата:" if idx == 0 else "..."
        text = f"{header}\n" + " ".join(chunk)
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def cmd_tag_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/tag_clear — reset the saved user list for this chat."""
    if not await is_admin(update, context):
        await update.message.reply_text("Только администраторы могут использовать /tag_clear.")
        return

    chat_id = update.effective_chat.id
    count = len(seen_users.pop(chat_id, {}))
    await update.message.reply_text(f"Список очищен. Было записано {count} пользователей.")


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Track every incoming message
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
    )

    app.add_handler(CommandHandler("tag", cmd_tag))
    app.add_handler(CommandHandler("tag_clear", cmd_tag_clear))

    logger.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
