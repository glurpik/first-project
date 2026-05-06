import asyncio
import json
import random
import httpx
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

BASE_URL = "https://www.kleinanzeigen.de"

GERMAN_STATES = [
    ("Baden-Württemberg",      "baden-wuerttemberg",      7970),
    ("Bayern",                  "bayern",                  5510),
    ("Berlin",                  "berlin",                  3331),
    ("Brandenburg",             "brandenburg",             7711),
    ("Bremen",                  "bremen",                     1),
    ("Hamburg",                 "hamburg",                 9409),
    ("Hessen",                  "hessen",                  4279),
    ("Mecklenburg-Vorpommern",  "mecklenburg-vorpommern",    61),
    ("Niedersachsen",           "niedersachsen",           2428),
    ("Nordrhein-Westfalen",     "nordrhein-westfalen",      928),
    ("Rheinland-Pfalz",         "rheinland-pfalz",         4938),
    ("Saarland",                "saarland",                 285),
    ("Sachsen",                 "sachsen",                 3799),
    ("Sachsen-Anhalt",          "sachsen-anhalt",          2165),
    ("Schleswig-Holstein",      "schleswig-holstein",       408),
    ("Thüringen",               "thueringen",              3548),
]

CATEGORIES = {
    "Вся электроника":        "elektronik",
    "Авто":                   "autos",
    "Мото":                   "motorraeder-roller",
    "Недвижимость":           "immobilien",
    "Одежда и мода":          "mode-beauty",
    "Дом и сад":              "haus-garten",
    "Дети и семья":           "familie-kind-baby",
    "Хобби и спорт":          "freizeit-hobbys-nachbarschaft",
    "Животные":               "tiere",
    "Бизнес и офис":          "buero-gewerbe",
    "Музыка":                 "musikinstrumente",
    "Телефоны":               "handys",
    "Компьютеры":             "computer",
    "Велосипеды":             "fahrraeder",
    "Все категории":          "anzeigen",
}

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


DETAIL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
}

SELLER_SELECTORS = [
    "#viewad-contact .userprofile-vip",
    ".userprofile--name",
    "a.userprofile-vip-link",
    "[data-testid='contact-name']",
]


async def _fetch_seller(client: httpx.AsyncClient, url: str) -> str:
    try:
        r = await client.get(url, timeout=8)
        if r.status_code != 200:
            return "Privat"
        soup = BeautifulSoup(r.text, "html.parser")
        for sel in SELLER_SELECTORS:
            el = soup.select_one(sel)
            if el:
                return el.get_text(strip=True)
        return "Privat"
    except Exception:
        return "Privat"


async def fill_seller_names(items: list[dict], concurrency: int = 10) -> None:
    """Параллельно заполняет seller_name для приватных продавцов через httpx."""
    need = [i for i in items if not i["seller_name"] and i["url"]]
    if not need:
        return

    async with httpx.AsyncClient(headers=DETAIL_HEADERS, follow_redirects=True) as client:
        sem = asyncio.Semaphore(concurrency)

        async def fetch_one(item):
            async with sem:
                item["seller_name"] = await _fetch_seller(client, item["url"])

        await asyncio.gather(*[fetch_one(item) for item in need])


def build_url(cat_slug: str, state_slug: str, loc_id: int, page: int) -> str:
    if page == 1:
        return f"{BASE_URL}/s-{state_slug}/{cat_slug}/k0l{loc_id}"
    return f"{BASE_URL}/s-{state_slug}/seite:{page}/{cat_slug}/k0l{loc_id}"


def get_seller_id(href: str) -> str:
    parts = href.rstrip("/").split("-")
    return parts[-1] if parts else ""


def parse_cards_from_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for card in soup.select("article.aditem"):
        ad_id = card.get("data-adid", "")
        href = card.get("data-href", "")

        title_el = card.select_one("h2 a.ellipsis")
        title = title_el.get_text(strip=True) if title_el else ""

        price_el = card.select_one("p.aditem-main--middle--price-shipping--price")
        price = price_el.get_text(strip=True) if price_el else ""

        location_el = card.select_one("div.aditem-main--top--left")
        location = location_el.get_text(strip=True) if location_el else ""

        date_el = card.select_one("div.aditem-main--top--right")
        date = date_el.get_text(strip=True) if date_el else ""

        # PRO-продавцы видны в карточке
        seller_name = ""
        seller_link = card.select_one("a.j-dont-follow-vip:not(.no-decoration)")
        if seller_link:
            span = seller_link.select_one("span")
            name = span.get_text(strip=True) if span else seller_link.get_text(strip=True)
            if name and name != "PRO":
                seller_name = name

        if not title and not price:
            continue

        results.append({
            "ad_id": ad_id,
            "seller_id": get_seller_id(href),
            "title": title,
            "price": price,
            "location": location,
            "date": date,
            "seller_name": seller_name,
            "url": f"{BASE_URL}{href}" if href else "",
        })
    return results


async def scrape_async(cat_slug: str, limit: int = 50) -> list[dict]:
    from playwright.async_api import async_playwright

    results = []
    seen_ads: set = set()
    seen_sellers: set = set()

    states = random.sample(GERMAN_STATES, len(GERMAN_STATES))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--ignore-certificate-errors", "--disable-blink-features=AutomationControlled"]
        )
        ctx = await browser.new_context(
            locale="de-DE",
            ignore_https_errors=True,
            viewport={"width": 1280, "height": 800},
            user_agent=random.choice(USER_AGENTS),
        )
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await ctx.new_page()

        for _, state_slug, loc_id in states:
            if len(results) >= limit:
                break

            for pg in range(1, 9):
                if len(results) >= limit:
                    break

                url = build_url(cat_slug, state_slug, loc_id, pg)
                try:
                    await page.goto(url, timeout=18000)
                    await page.wait_for_selector("article.aditem", timeout=7000)
                except Exception:
                    break  # эта земля не отвечает — следующая

                html = await page.content()
                cards = parse_cards_from_html(html)
                if not cards:
                    break

                for card in cards:
                    if len(results) >= limit:
                        break
                    if card["ad_id"] in seen_ads:
                        continue
                    if card["seller_id"] and card["seller_id"] in seen_sellers:
                        continue
                    seen_ads.add(card["ad_id"])
                    if card["seller_id"]:
                        seen_sellers.add(card["seller_id"])
                    results.append(card)

                soup = BeautifulSoup(html, "html.parser")
                if not soup.select_one("a.pagination-next"):
                    break

                # Минимальная пауза между страницами
                await asyncio.sleep(0.5)

            # Небольшая пауза между землями
            await asyncio.sleep(0.3)

        await browser.close()

    # Параллельно получаем имена приватных продавцов через httpx
    await fill_seller_names(results[:limit])

    return results[:limit]


def scrape(cat_slug: str, limit: int = 50) -> list[dict]:
    return asyncio.run(scrape_async(cat_slug, limit))


def _format_row(i: dict) -> dict:
    return {
        "Название": i["title"],
        "Ссылка на объявление": i["url"],
        "Цена": i["price"],
        "Имя продавца": i["seller_name"],
        "Дата создания": i["date"],
        "Город": i["location"],
    }


def save_json(data: list[dict], path: str = "results.json") -> str:
    Path(path).write_text(json.dumps([_format_row(i) for i in data], ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_xlsx(data: list[dict], path: str = "results.xlsx") -> str:
    pd.DataFrame([_format_row(i) for i in data]).to_excel(path, index=False)
    return path
