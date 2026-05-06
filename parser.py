import asyncio
import json
import random
import re
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

BASE_URL = "https://www.kleinanzeigen.de"

# 16 федеральных земель Германии: (название, slug, location_id)
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


def build_url(cat_slug: str, state_slug: str, loc_id: int, page: int) -> str:
    """Строит URL вида /s-{state}/seite:N/{cat}/k0l{loc_id}"""
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


async def fetch_seller_name_pw(page, url: str) -> str:
    try:
        await page.goto(url, timeout=15000)
        await page.wait_for_selector("#viewad-contact, .userprofile-vip", timeout=6000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        for sel in ["#viewad-contact .userprofile-vip", ".userprofile--name", "[data-testid='contact-name']"]:
            el = soup.select_one(sel)
            if el:
                return el.get_text(strip=True)
        return "Privat"
    except Exception:
        return "Privat"


async def scrape_async(cat_slug: str, limit: int = 50) -> list[dict]:
    from playwright.async_api import async_playwright

    results = []
    seen_ads = set()
    seen_sellers = set()

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

        list_page = await ctx.new_page()
        detail_page = await ctx.new_page()

        for state_name, state_slug, loc_id in states:
            if len(results) >= limit:
                break

            for pg in range(1, 9):  # до 8 страниц на землю
                if len(results) >= limit:
                    break

                url = build_url(cat_slug, state_slug, loc_id, pg)

                try:
                    await list_page.goto(url, timeout=20000)
                    await list_page.wait_for_selector("article.aditem", timeout=8000)
                    await asyncio.sleep(random.uniform(0.5, 1.2))
                except Exception:
                    break  # эта земля заблокирована, следующая

                html = await list_page.content()
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

                    if not card["seller_name"] and card["url"]:
                        card["seller_name"] = await fetch_seller_name_pw(detail_page, card["url"])
                        await asyncio.sleep(random.uniform(0.3, 0.7))

                    results.append(card)

                # Проверяем есть ли следующая страница
                soup = BeautifulSoup(html, "html.parser")
                if not soup.select_one("a.pagination-next"):
                    break

                await asyncio.sleep(random.uniform(1.5, 2.5))

            await asyncio.sleep(random.uniform(1.0, 2.0))

        await browser.close()

    return results


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
