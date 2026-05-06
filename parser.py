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
    # URL формат: /s-anzeige/title/ADID-CATID-SELLERID
    parts = href.rstrip("/").split("-")
    return parts[-1] if parts else ""


def parse_card(card) -> dict:
    ad_id = card.get("data-adid", "")
    href = card.get("data-href", "")
    seller_id = get_seller_id(href)

    title_el = card.select_one("h2 a.ellipsis")
    title = title_el.get_text(strip=True) if title_el else ""

    desc_el = card.select_one("p.aditem-main--middle--description")
    description = desc_el.get_text(strip=True) if desc_el else ""

    price_el = card.select_one("p.aditem-main--middle--price-shipping--price")
    price = price_el.get_text(strip=True) if price_el else ""

    location_el = card.select_one("div.aditem-main--top--left")
    location = location_el.get_text(strip=True) if location_el else ""

    date_el = card.select_one("div.aditem-main--top--right")
    date = date_el.get_text(strip=True) if date_el else ""

    img_el = card.select_one("img")
    image = img_el.get("src", "") if img_el else ""

    return {
        "id": ad_id,
        "seller_id": seller_id,
        "title": title,
        "price": price,
        "location": location,
        "date": date,
        "description": description,
        "url": f"{BASE_URL}{href}" if href else "",
        "image": image,
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
                # вставляем seite:N перед /k0
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

                # Черный список: пропускаем повторных продавцов
                if item["seller_id"] and item["seller_id"] in seen_sellers:
                    continue

                if item["seller_id"]:
                    seen_sellers.add(item["seller_id"])

                results.append(item)

            has_next = soup.select_one("a.pagination-next")
            if not has_next:
                break

            page += 1
            if len(results) < limit:
                time.sleep(delay)

    return results


def save_json(data: list[dict], path: str = "results.json") -> str:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_xlsx(data: list[dict], path: str = "results.xlsx") -> str:
    df = pd.DataFrame(data)
    df.to_excel(path, index=False)
    return path
