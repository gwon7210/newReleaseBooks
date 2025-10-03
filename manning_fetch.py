import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Union

import requests

API_URL = "https://www.manning.com/search/getCatalogData"
OUTPUT_FILE = "manning_books.json"
COVER_BASE = "https://images.manning.com/320/400/resize/"
DEFAULT_PAYLOAD: Dict[str, Union[str, int, bool, List[str]]] = {
    "accessType": [],
    "keywords": [],
    "level": [],
    "meapFilter": "meap",
    "productType": ["book"],
    "programmingLanguages": [],
    "selectedCategoryIds": [1],
    "sort": "newest",
    "includePrices": True,
    "page": 1,
}

logging.basicConfig(level=logging.INFO, format="%(message)s")


def fetch_catalog(payload: Dict[str, Union[str, int, List[str]]]) -> Union[Dict, List]:
    response = requests.post(API_URL, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def flatten_items(data: Union[Dict, List]) -> List[Dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ("items", "results", "products", "data", "payload", "catalog"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested_items = flatten_items(value)
                if nested_items:
                    return nested_items
    return []


def build_cover_url(raw_url: str) -> str:
    if not raw_url:
        return ""
    raw_url = raw_url.lstrip("/")
    return f"{COVER_BASE}{raw_url}"


def transform_item(item: Dict) -> Dict[str, str]:
    title = item.get("title") or item.get("name") or ""
    link = item.get("link") or ""
    cover_image = build_cover_url(str(item.get("imageUrl") or ""))

    return {
        "title": title,
        "detail_link": link,
        "cover_image": cover_image,
    }


def save_items(items: Iterable[Dict[str, str]], output_path: Path) -> None:
    data = list(items)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Saved %s books to %s", len(data), output_path)


def main() -> None:
    payload = DEFAULT_PAYLOAD.copy()
    try:
        raw = fetch_catalog(payload)
    except requests.HTTPError as exc:
        logging.error("HTTP error fetching Manning catalog: %s", exc)
        raise
    except requests.RequestException as exc:
        logging.error("Network error fetching Manning catalog: %s", exc)
        raise

    items = flatten_items(raw)
    if not items and isinstance(raw, dict) and "catalog" in raw:
        items = flatten_items(raw["catalog"])

    if not items:
        logging.warning("No catalog items found in response")

    books: List[Dict[str, str]] = []
    for item in items:
        transformed = transform_item(item)
        if transformed["title"]:
            books.append(transformed)
    save_items(books, Path(OUTPUT_FILE))


if __name__ == "__main__":
    main()
