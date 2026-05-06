import asyncio
import tempfile
import logging
import time
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession

from parser import scrape, save_json, save_xlsx, CATEGORIES, get_browser

BOT_TOKEN = "8621692689:AAHQ8nznAi3k7ibGBQ0fCDw_jGf-dIykaYM"

logging.basicConfig(level=logging.INFO)

_session = AiohttpSession()
_session._connector_init["ssl"] = False
bot = Bot(token=BOT_TOKEN, session=_session)
dp = Dispatcher(storage=MemoryStorage())

LIMITS = [20, 50, 100, 200, 500]

# ── Очередь и кэш ──────────────────────────────────────────────────────────
# Только 1 задача парсинга в одно время (один браузер, один IP)
_scrape_semaphore = asyncio.Semaphore(1)

# Кэш результатов: ключ → (timestamp, data)
# Одинаковый запрос (категория + лимит) в течение 5 минут отдаётся из кэша
_cache: dict[str, tuple[float, list]] = {}
CACHE_TTL = 300  # секунд


def _cache_get(key: str) -> list | None:
    if key in _cache:
        ts, data = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _cache[key]
    return None


def _cache_set(key: str, data: list) -> None:
    _cache[key] = (time.time(), data)


async def get_items(cat_slug: str, limit: int) -> tuple[list, bool]:
    """Возвращает (items, from_cache). Параллельные запросы ждут в очереди."""
    key = f"{cat_slug}:{limit}"

    cached = _cache_get(key)
    if cached is not None:
        return cached, True

    async with _scrape_semaphore:
        # Пока ждали — может уже кто-то положил в кэш
        cached = _cache_get(key)
        if cached is not None:
            return cached, True

        items = await scrape(cat_slug, limit=limit)
        if items:
            _cache_set(key, items)
        return items, False


# ── Клавиатуры ─────────────────────────────────────────────────────────────

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
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=str(l), callback_data=f"limit:{category}:{l}")
        for l in LIMITS
    ]])


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


# ── Хэндлеры ───────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "👋 <b>Kleinanzeigen Parser</b>\n\nВыбери категорию:",
        parse_mode="HTML",
        reply_markup=categories_keyboard()
    )


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
    cat_slug = CATEGORIES[category]

    # Показываем позицию в очереди если семафор занят
    queue_pos = _scrape_semaphore._value  # 0 = занят, 1 = свободен
    wait_msg = "" if queue_pos > 0 else "\n<i>⏳ Ожидаю завершения другого запроса...</i>"

    await call.message.edit_text(
        f"🔍 Собираю <b>{limit}</b> объявлений | «{category}»...{wait_msg}",
        parse_mode="HTML"
    )
    await call.answer()

    items, from_cache = await get_items(cat_slug, limit)

    if not items:
        await call.message.edit_text(
            "❌ Ничего не найдено. Сайт временно заблокировал запросы — попробуй через 5 минут."
        )
        return

    cache_note = " <i>(из кэша)</i>" if from_cache else ""
    lines = [f"✅ Собрано <b>{len(items)}</b> объявлений | {category}{cache_note}\n"]
    for i, item in enumerate(items[:10], 1):
        lines.append(format_item(item, i))
    if len(items) > 10:
        lines.append(f"\n<i>...и ещё {len(items) - 10}. Скачай файл.</i>")
    lines.append("\n<i>⚫ Повторные продавцы исключены</i>")

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

    items, _ = await get_items(CATEGORIES[category], limit)
    path = tempfile.mktemp(suffix=".json")
    save_json(items, path)
    safe_name = category.replace(" ", "_")
    await call.message.answer_document(
        FSInputFile(path, filename=f"{safe_name}_{limit}.json"),
        caption=f"📄 {len(items)} объявлений | {category}"
    )


@dp.callback_query(F.data.startswith("xlsx:"))
async def cb_xlsx(call: CallbackQuery):
    _, category, limit_str = call.data.split(":", 2)
    limit = int(limit_str)
    await call.answer("Генерирую XLSX...")

    items, _ = await get_items(CATEGORIES[category], limit)
    path = tempfile.mktemp(suffix=".xlsx")
    save_xlsx(items, path)
    safe_name = category.replace(" ", "_")
    await call.message.answer_document(
        FSInputFile(path, filename=f"{safe_name}_{limit}.xlsx"),
        caption=f"📊 {len(items)} объявлений | {category}"
    )


@dp.message(F.text & ~F.text.startswith("/"))
async def handle_text(msg: Message):
    await msg.answer("Выбери категорию:", reply_markup=categories_keyboard())


async def main():
    # Прогреваем браузер при старте — первый запрос будет мгновенным
    await get_browser()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
