"""
Автоматический поиск каналов с розыгрышами:
1. Список крупных RU компаний (хардкод)
2. Глобальный поиск по Telegram
3. Парсинг tgstat.ru/ru/posts - каталог постов с розыгрышами
"""

import asyncio
import logging
import re
import aiosqlite
import aiohttp
from telethon import TelegramClient
from telethon.tl.functions.contacts import SearchRequest
from telethon.errors import FloodWaitError

log = logging.getLogger(__name__)

DB_FILE = "research.db"

# Крупные российские компании и бренды с официальными TG-каналами
MAJOR_RU_BRANDS = [
    # Ритейл / маркетплейсы
    "ozon", "wildberries_official", "sbermegamarket", "lamoda",
    "mvideo_official", "eldorado_official", "dns_official",
    # Еда / доставка
    "vkusvill", "magnit_official", "pyaterochka", "lenta_official",
    "dodopizza", "kfc_russia", "mcdonalds_russia", "burger_king_rus",
    "yandex_eda", "delivery_club",
    # Банки / финансы
    "sberbank", "tinkoff_bank", "vtb_official", "alfabank",
    "raiffeisen_russia", "gazprombank",
    # Техника / телеком
    "beeline_official", "megafon", "mts_official", "tele2russia",
    "samsung_russia", "apple_russia_official",
    # Авто
    "avtovaz_official", "lada_official",
    # Медиа / развлечения
    "kinopoisk", "ivi_official", "okko_tv",
    # Косметика / аптеки
    "letual_official", "rive_gauche", "eapteka_official",
    # Одежда
    "gloria_jeans", "befree_official", "zara_russia",
    # Спорт
    "sportmaster_official", "decathlon_russia",
    # Прочее
    "yandex", "vk", "mail_ru_official",
]

SEARCH_QUERIES = [
    "розыгрыш приз",
    "giveaway конкурс",
    "разыгрываем приз",
    "выиграй приз",
    "бесплатный розыгрыш",
    "конкурс подарки",
    "розыгрыш среди подписчиков",
]


async def init_channels_table():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS known_channels (
                username TEXT PRIMARY KEY,
                source TEXT,
                added_at TEXT,
                active INTEGER DEFAULT 1
            )
        """)
        await db.commit()


async def save_channel(username: str, source: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO known_channels (username, source, added_at) VALUES (?,?,datetime('now'))",
            (username.lower().strip("@"), source)
        )
        await db.commit()


async def get_all_channels() -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute(
            "SELECT username FROM known_channels WHERE active=1"
        )
        rows = await cursor.fetchall()
    return [r[0] for r in rows]


async def load_brand_channels():
    """Загружает список крупных RU брендов в БД."""
    for username in MAJOR_RU_BRANDS:
        await save_channel(username, "major_ru_brand")
    log.info(f"Загружено {len(MAJOR_RU_BRANDS)} каналов крупных RU брендов")


async def search_telegram_channels(client: TelegramClient):
    """Ищет каналы через встроенный поиск Telegram."""
    found = 0
    for query in SEARCH_QUERIES:
        try:
            result = await client(SearchRequest(q=query, limit=20))
            for chat in result.chats:
                username = getattr(chat, "username", None)
                if username:
                    await save_channel(username, f"tg_search:{query}")
                    found += 1
            await asyncio.sleep(3)  # Пауза между поисками
        except FloodWaitError as e:
            log.warning(f"FloodWait {e.seconds}s при поиске '{query}'")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            log.warning(f"Ошибка поиска '{query}': {e}")

    log.info(f"Найдено через TG Search: {found} каналов")


async def scrape_tgstat(proxy: dict = None):
    """
    Парсит tgstat.ru/ru/posts?q=розыгрыш — публичный каталог постов.
    Извлекает юзернеймы каналов из результатов.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
    queries = ["розыгрыш", "конкурс", "giveaway", "выиграй приз"]
    found = 0

    connector = None
    if proxy:
        # Поддержка HTTP прокси для парсинга
        connector = aiohttp.TCPConnector()

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        for query in queries:
            try:
                url = f"https://tgstat.ru/ru/posts?q={query}&peerType=channel"
                proxy_url = None
                if proxy and proxy.get("type") == "http":
                    proxy_url = f"http://{proxy.get('addr')}:{proxy.get('port')}"

                async with session.get(url, proxy=proxy_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()

                # Извлекаем юзернеймы каналов из HTML
                usernames = re.findall(r't\.me/([\w_]+)', text)
                usernames += re.findall(r'@([\w_]{4,})', text)

                for u in set(usernames):
                    if len(u) > 3 and u not in ("ru", "com", "org", "me", "tgstat"):
                        await save_channel(u, f"tgstat:{query}")
                        found += 1

                await asyncio.sleep(5)  # Вежливый парсинг
            except Exception as e:
                log.warning(f"Ошибка парсинга tgstat для '{query}': {e}")

    log.info(f"Найдено через tgstat.ru: {found} каналов")


def extract_channels_from_post(text: str) -> list:
    """Извлекает упомянутые каналы из поста розыгрыша для дальнейшего мониторинга."""
    usernames = []
    patterns = [
        r"@([\w_]{4,})",
        r"t\.me/([\w_]+)",
    ]
    for p in patterns:
        for m in re.findall(p, text, re.IGNORECASE):
            if m.lower() not in usernames:
                usernames.append(m.lower())
    return usernames


async def run_discovery(client: TelegramClient, proxy: dict = None):
    """Полный цикл обнаружения каналов."""
    await init_channels_table()
    await load_brand_channels()
    await search_telegram_channels(client)
    await scrape_tgstat(proxy)

    total = len(await get_all_channels())
    log.info(f"Итого каналов для мониторинга: {total}")
    return total
