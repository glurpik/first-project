import asyncio
import tempfile
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from parser import scrape, save_json, save_xlsx

BOT_TOKEN = "8621692689:AAHQ8nznAi3k7ibGBQ0fCDw_jGf-dIykaYM"

logging.basicConfig(level=logging.INFO)

_session = AiohttpSession()
_session._connector_init["ssl"] = False
bot = Bot(token=BOT_TOKEN, session=_session)
dp = Dispatcher(storage=MemoryStorage())


class SearchState(StatesGroup):
    waiting_query = State()


def format_item(i: dict, n: int) -> str:
    price = i["price"] or "—"
    date = f" | {i['date']}" if i["date"] else ""
    return (
        f"<b>{n}. {i['title'] or 'Без названия'}</b>\n"
        f"💶 {price} | 📍 {i['location']}{date}\n"
        f"🔗 <a href=\"{i['url']}\">Открыть</a>\n"
    )


def export_keyboard(query: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📄 JSON", callback_data=f"json:{query}"),
        InlineKeyboardButton(text="📊 XLSX", callback_data=f"xlsx:{query}"),
    ]])


@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "👋 <b>Kleinanzeigen Parser</b>\n\n"
        "Отправь поисковый запрос — найду объявления на kleinanzeigen.de\n\n"
        "Команды:\n"
        "/search — поиск объявлений\n"
        "/help — справка",
        parse_mode="HTML"
    )


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "<b>Как пользоваться:</b>\n\n"
        "1. Просто напиши запрос, например: <code>iphone 15</code>\n"
        "2. Получишь список объявлений\n"
        "3. Нажми кнопку JSON или XLSX чтобы скачать файл\n\n"
        "<b>Примеры запросов:</b>\n"
        "• <code>iphone 15</code>\n"
        "• <code>macbook pro</code>\n"
        "• <code>fahrrad</code> (велосипед)\n"
        "• <code>sofa</code>\n\n"
        "По умолчанию парсится 2 страницы (~50 объявлений)",
        parse_mode="HTML"
    )


@dp.message(Command("search"))
async def cmd_search(msg: Message, state: FSMContext):
    await msg.answer("Введи поисковый запрос:")
    await state.set_state(SearchState.waiting_query)


@dp.message(SearchState.waiting_query)
async def handle_state_query(msg: Message, state: FSMContext):
    await state.clear()
    await do_search(msg, msg.text.strip())


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: Message):
    await do_search(msg, msg.text.strip())


async def do_search(msg: Message, query: str):
    status = await msg.answer(f"🔍 Ищу <b>{query}</b>...", parse_mode="HTML")

    items = await asyncio.get_event_loop().run_in_executor(
        None, lambda: scrape(query, max_pages=2)
    )

    await status.delete()

    if not items:
        await msg.answer("❌ Ничего не найдено. Попробуй другой запрос.")
        return

    lines = [f"✅ Найдено <b>{len(items)}</b> объявлений по запросу «{query}»:\n"]
    for i, item in enumerate(items[:10], 1):
        lines.append(format_item(item, i))

    if len(items) > 10:
        lines.append(f"\n<i>...и ещё {len(items) - 10}. Скачай файл чтобы увидеть все.</i>")

    await msg.answer(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=export_keyboard(query),
    )


@dp.callback_query(F.data.startswith("json:"))
async def cb_json(call: CallbackQuery):
    query = call.data.split(":", 1)[1]
    await call.answer("Генерирую JSON...")

    items = await asyncio.get_event_loop().run_in_executor(
        None, lambda: scrape(query, max_pages=2)
    )

    path = tempfile.mktemp(suffix=".json")
    save_json(items, path)

    await call.message.answer_document(
        FSInputFile(path, filename=f"{query}.json"),
        caption=f"📄 {len(items)} объявлений | {query}"
    )


@dp.callback_query(F.data.startswith("xlsx:"))
async def cb_xlsx(call: CallbackQuery):
    query = call.data.split(":", 1)[1]
    await call.answer("Генерирую XLSX...")

    items = await asyncio.get_event_loop().run_in_executor(
        None, lambda: scrape(query, max_pages=2)
    )

    path = tempfile.mktemp(suffix=".xlsx")
    save_xlsx(items, path)

    await call.message.answer_document(
        FSInputFile(path, filename=f"{query}.xlsx"),
        caption=f"📊 {len(items)} объявлений | {query}"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
