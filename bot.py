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

from parser import scrape, save_json, save_xlsx, CATEGORIES

BOT_TOKEN = "8621692689:AAHQ8nznAi3k7ibGBQ0fCDw_jGf-dIykaYM"

logging.basicConfig(level=logging.INFO)

_session = AiohttpSession()
_session._connector_init["ssl"] = False
bot = Bot(token=BOT_TOKEN, session=_session)
dp = Dispatcher(storage=MemoryStorage())

LIMITS = [20, 50, 100, 200, 500]


class SearchState(StatesGroup):
    choose_category = State()
    choose_limit = State()


def categories_keyboard() -> InlineKeyboardMarkup:
    buttons = []
    cats = list(CATEGORIES.keys())
    for i in range(0, len(cats), 2):
        row = [InlineKeyboardButton(text=cats[i], callback_data=f"cat:{cats[i]}")]
        if i + 1 < len(cats):
            row.append(InlineKeyboardButton(text=cats[i + 1], callback_data=f"cat:{cats[i + 1]}"))
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def limits_keyboard(category: str) -> InlineKeyboardMarkup:
    buttons = [[
        InlineKeyboardButton(text=str(l), callback_data=f"limit:{category}:{l}")
        for l in LIMITS
    ]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def export_keyboard(category: str, limit: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📄 JSON", callback_data=f"json:{category}:{limit}"),
        InlineKeyboardButton(text="📊 XLSX", callback_data=f"xlsx:{category}:{limit}"),
    ]])


def format_item(item: dict, n: int) -> str:
    price = item["price"] or "—"
    date = f" | {item['date']}" if item["date"] else ""
    return (
        f"<b>{n}. {item['title'] or 'Без названия'}</b>\n"
        f"💶 {price} | 📍 {item['location']}{date}\n"
        f"🔗 <a href=\"{item['url']}\">Открыть</a>\n"
    )


@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "👋 <b>Kleinanzeigen Parser</b>\n\n"
        "Выбери категорию для поиска:",
        parse_mode="HTML",
        reply_markup=categories_keyboard()
    )


@dp.message(Command("categories"))
async def cmd_categories(msg: Message):
    await msg.answer("Выбери категорию:", reply_markup=categories_keyboard())


@dp.callback_query(F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery):
    category = call.data.split(":", 1)[1]
    await call.message.edit_text(
        f"Категория: <b>{category}</b>\n\nСколько объявлений собрать?",
        parse_mode="HTML",
        reply_markup=limits_keyboard(category)
    )
    await call.answer()


@dp.callback_query(F.data.startswith("limit:"))
async def cb_limit(call: CallbackQuery):
    _, category, limit_str = call.data.split(":", 2)
    limit = int(limit_str)

    await call.message.edit_text(
        f"🔍 Собираю <b>{limit}</b> объявлений в категории «{category}»...\n"
        f"<i>Это может занять до {limit // 10} секунд</i>",
        parse_mode="HTML"
    )
    await call.answer()

    category_path = CATEGORIES[category]
    items = await asyncio.get_event_loop().run_in_executor(
        None, lambda: scrape(category_path, limit=limit)
    )

    if not items:
        await call.message.edit_text("❌ Ничего не найдено. Попробуй другую категорию.")
        return

    lines = [f"✅ Собрано <b>{len(items)}</b> объявлений | {category}\n"]
    for i, item in enumerate(items[:10], 1):
        lines.append(format_item(item, i))

    if len(items) > 10:
        lines.append(f"\n<i>...и ещё {len(items) - 10}. Скачай файл чтобы увидеть все.</i>")

    lines.append("\n<i>⚫ Повторные продавцы исключены автоматически</i>")

    await call.message.edit_text(
        "\n".join(lines),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=export_keyboard(category, limit)
    )


@dp.callback_query(F.data.startswith("json:"))
async def cb_json(call: CallbackQuery):
    _, category, limit_str = call.data.split(":", 2)
    limit = int(limit_str)
    await call.answer("Генерирую JSON...")

    category_path = CATEGORIES[category]
    items = await asyncio.get_event_loop().run_in_executor(
        None, lambda: scrape(category_path, limit=limit)
    )

    path = tempfile.mktemp(suffix=".json")
    save_json(items, path)
    safe_name = category.replace(" ", "_").replace("/", "-")
    await call.message.answer_document(
        FSInputFile(path, filename=f"{safe_name}_{limit}.json"),
        caption=f"📄 {len(items)} объявлений | {category}"
    )


@dp.callback_query(F.data.startswith("xlsx:"))
async def cb_xlsx(call: CallbackQuery):
    _, category, limit_str = call.data.split(":", 2)
    limit = int(limit_str)
    await call.answer("Генерирую XLSX...")

    category_path = CATEGORIES[category]
    items = await asyncio.get_event_loop().run_in_executor(
        None, lambda: scrape(category_path, limit=limit)
    )

    path = tempfile.mktemp(suffix=".xlsx")
    save_xlsx(items, path)
    safe_name = category.replace(" ", "_").replace("/", "-")
    await call.message.answer_document(
        FSInputFile(path, filename=f"{safe_name}_{limit}.xlsx"),
        caption=f"📊 {len(items)} объявлений | {category}"
    )


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: Message):
    await msg.answer(
        "Выбери категорию для поиска:",
        reply_markup=categories_keyboard()
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
