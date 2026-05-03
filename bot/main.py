import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
import config
from handlers import user, admin, chat_member

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def scheduled_leaderboard_refresh():
    await db.refresh_leaderboard()
    config.set_leaderboard_updated()
    logger.info("Leaderboard refreshed")


async def main():
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set in .env")

    await db.init_db()

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(chat_member.router)
    dp.include_router(admin.router)
    dp.include_router(user.router)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_leaderboard_refresh,
        trigger="interval",
        seconds=config.LEADERBOARD_UPDATE_INTERVAL,
        id="leaderboard_refresh"
    )
    scheduler.start()

    logger.info("Bot started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])


if __name__ == "__main__":
    asyncio.run(main())
