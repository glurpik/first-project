import httpx
import time
import json
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

BASE_URL = "https://www.kleinanzeigen.de"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CATEGORIES = {
    "Вся электроника":        "/s-elektronik/k0",
    "Авто":                   "/s-autos/k0",
    "Мото":                   "/s-motorraeder-roller/k0",
    "Недвижимость":           "/s-immobilien/k0",
    "Одежда и мода":          "/s-mode-beauty/k0",
    "Дом и сад":              "/s-haus-garten/k0",
    "Дети и семья":           "/s-familie-kind-baby/k0",
    "Хобби и спорт":          "/s-freizeit-hobbys-nachbarschaft/k0",
    "Животные":               "/s-tiere/k0",
    "Бизнес и офис":          "/s-buero-gewerbe/k0",
    "Музыка":                 "/s-musikinstrumente/k0",
    "Телефоны":               "/s-handys/k0",
    "Компьютеры":             "/s-computer/k0",
    "Велосипеды":             "/s-fahrraeder/k0",
    "Все категории":          "/s-anzeigen/k0",
}


def get_seller_id(href: str) -> str:
    parts = href.rstrip("/").split("-")
    return parts[-1] if parts else ""


def extract_seller_name_from_card(card) -> str:
    """Извлекает имя продавца из карточки (только PRO продавцы видны в карточке)."""
    seller_link = card.select_one("a.j-dont-follow-vip:not(.no-decoration)")
    if seller_link:
        span = seller_link.select_one("span")
        name = span.get_text(strip=True) if span else seller_link.get_text(strip=True)
        if name and name != "PRO":
            return name
    return ""


def fetch_seller_name(client: httpx.Client, url: str) -> str:
    """Заходит на страницу объявления и достаёт имя продавца."""
    try:
        r = client.get(url, timeout=10)
        if r.status_code != 200:
            return "Privat"
        soup = BeautifulSoup(r.text, "html.parser")
        # Имя продавца на странице объявления
        el = soup.select_one("#viewad-contact .userprofile-vip, #viewad-contact a[href*='/s-bestandslisten/'], .userprofile--name, [data-testid='contact-name']")
        if el:
            return el.get_text(strip=True)
        # Запасной вариант
        el2 = soup.select_one("a.user-profile-vip, .userprofile-vip-link")
        if el2:
            return el2.get_text(strip=True)
        return "Privat"
    except Exception:
        return "Privat"


def parse_card(card) -> dict:
    ad_id = card.get("data-adid", "")
    href = card.get("data-href", "")
    seller_id = get_seller_id(href)

    title_el = card.select_one("h2 a.ellipsis")
    title = title_el.get_text(strip=True) if title_el else ""

    price_el = card.select_one("p.aditem-main--middle--price-shipping--price")
    price = price_el.get_text(strip=True) if price_el else ""

    location_el = card.select_one("div.aditem-main--top--left")
    location = location_el.get_text(strip=True) if location_el else ""

    date_el = card.select_one("div.aditem-main--top--right")
    date = date_el.get_text(strip=True) if date_el else ""

    seller_name = extract_seller_name_from_card(card)

    return {
        "seller_id": seller_id,
        "title": title,
        "price": price,
        "location": location,
        "date": date,
        "seller_name": seller_name,
        "url": f"{BASE_URL}{href}" if href else "",
    }


def scrape(category_path: str, limit: int = 50, delay: float = 1.0) -> list[dict]:
    results = []
    seen_sellers = set()
    page = 1

    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        while len(results) < limit:
            if page == 1:
                url = f"{BASE_URL}{category_path}"
            else:
                url = f"{BASE_URL}{category_path.replace('/k0', f'/seite:{page}/k0')}"

            resp = client.get(url)
            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("article.aditem")

            if not cards:
                break

            for card in cards:
                if len(results) >= limit:
                    break

                item = parse_card(card)

                if not item["title"] and not item["price"]:
                    continue

                # Чёрный список: один продавец — одно объявление
                if item["seller_id"] and item["seller_id"] in seen_sellers:
                    continue
                if item["seller_id"]:
                    seen_sellers.add(item["seller_id"])

                # Если имя не найдено в карточке — идём на страницу объявления
                if not item["seller_name"] and item["url"]:
                    item["seller_name"] = fetch_seller_name(client, item["url"])
                    time.sleep(0.3)

                results.append(item)

            has_next = soup.select_one("a.pagination-next")
            if not has_next:
                break

            page += 1
            if len(results) < limit:
                time.sleep(delay)

    return results


def save_json(data: list[dict], path: str = "results.json") -> str:
    export = [
        {
            "Название": i["title"],
            "Ссылка на объявление": i["url"],
            "Цена": i["price"],
            "Имя продавца": i["seller_name"],
            "Дата создания": i["date"],
            "Город": i["location"],
        }
        for i in data
    ]
    Path(path).write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_xlsx(data: list[dict], path: str = "results.xlsx") -> str:
    rows = [
        {
            "Название": i["title"],
            "Ссылка на объявление": i["url"],
            "Цена": i["price"],
            "Имя продавца": i["seller_name"],
            "Дата создания": i["date"],
            "Город": i["location"],
        }
        for i in data
    ]
    df = pd.DataFrame(rows)
    df.to_excel(path, index=False)
    return path
