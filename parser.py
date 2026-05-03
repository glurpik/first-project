import httpx
import time
import json
import re
from bs4 import BeautifulSoup
import pandas as pd
from pathlib import Path

BASE_URL = "https://www.kleinanzeigen.de"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def build_search_url(query: str, category: str = "", page: int = 1) -> str:
    keyword = query.strip().replace(" ", "-")
    cat = f"-{category}" if category else ""
    page_part = f"/seite:{page}" if page > 1 else ""
    return f"{BASE_URL}/s-{keyword}{cat}{page_part}/k0"


def parse_card(card) -> dict:
    ad_id = card.get("data-adid", "")
    href = card.get("data-href", "")

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
        "title": title,
        "price": price,
        "location": location,
        "date": date,
        "description": description,
        "url": f"{BASE_URL}{href}" if href else "",
        "image": image,
    }


def scrape(query: str, category: str = "", max_pages: int = 3, delay: float = 1.0) -> list[dict]:
    results = []

    with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
        for page in range(1, max_pages + 1):
            url = build_search_url(query, category, page)
            resp = client.get(url)

            if resp.status_code != 200:
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("article.aditem")

            if not cards:
                break

            for card in cards:
                item = parse_card(card)
                if item["title"] or item["price"]:
                    results.append(item)

            has_next = soup.select_one("a.pagination-next")
            if not has_next:
                break

            if page < max_pages:
                time.sleep(delay)

    return results


def save_json(data: list[dict], path: str = "results.json") -> str:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_xlsx(data: list[dict], path: str = "results.xlsx") -> str:
    df = pd.DataFrame(data)
    df.to_excel(path, index=False)
    return path


if __name__ == "__main__":
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "iphone"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    print(f"Парсим: '{query}', страниц: {pages}")
    items = scrape(query, max_pages=pages)
    print(f"Найдено: {len(items)} объявлений")

    save_json(items, "results.json")
    save_xlsx(items, "results.xlsx")
    print("Сохранено: results.json, results.xlsx")
