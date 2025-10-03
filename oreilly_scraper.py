import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

TARGET_URL = "https://www.oreilly.com/search/?q=*&type=book&publishers=O%27Reilly%20Media%2C%20Inc.&rows=100&order_by=published_at"
OUTPUT_FILE = "oreilly_books.json"
PUBLISHED_AT_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+"
    r"(?:\d{1,2},\s*)?\d{4}",
    re.IGNORECASE,
)


def _ensure_chromedriver_binary(path: str) -> str:
    candidate = Path(path)
    if candidate.name.startswith("THIRD_PARTY_NOTICES"):
        sibling = candidate.with_name("chromedriver")
        if sibling.exists():
            return str(sibling)
        sibling = candidate.parent / "chromedriver"
        if sibling.exists():
            return str(sibling)
    return str(candidate)


def setup_driver() -> webdriver.Chrome:
    """Create a headless Chrome webdriver configured for CI environments."""
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,1024")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

    if "GITHUB_ACTIONS" in os.environ:
        chrome_binary_candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
        ]
        for binary in chrome_binary_candidates:
            if os.path.exists(binary):
                chrome_options.binary_location = binary
                break

    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as manager_error:
        print(f"Falling back to webdriver_manager due to: {manager_error}")
        driver_path = _ensure_chromedriver_binary(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=Service(driver_path), options=chrome_options)
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(10)
    return driver


def clean_text(value: str) -> str:
    if not value:
        return ""
    return " ".join(value.split())


def parse_books(page_source: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(page_source, "html.parser")
    cards = soup.select('[data-testid^="search-card"]')
    dedup: Dict[str, Dict[str, str]] = {}

    for card in cards:
        title_elem = card.select_one("h4.title") or card.select_one("a.MuiTypography-link")
        title = clean_text(title_elem.get_text()) if title_elem else ""

        if not title:
            continue

        desc_elem = card.select_one('[data-testid^="search-card-description"]')
        description = clean_text(desc_elem.get_text()) if desc_elem else ""

        published_at = ""
        for footer in card.select(".MuiTypography-cardFooter"):
            footer_text = clean_text(footer.get_text())
            if not footer_text:
                continue
            normalized = footer_text
            if "출판일" in normalized:
                normalized = normalized.split(":", 1)[-1].strip()
            if "page" in normalized.lower():
                continue
            if PUBLISHED_AT_PATTERN.search(normalized):
                published_at = normalized
                break
            if not published_at and footer_text and "출판일" in footer_text:
                published_at = normalized

        if not published_at:
            alt_elem = card.select_one('[data-testid*="published"]')
            if alt_elem:
                alt_text = clean_text(alt_elem.get_text())
                if alt_text:
                    if "출판일" in alt_text:
                        alt_text = alt_text.split(":", 1)[-1].strip()
                    published_at = alt_text

        detail_elem = card.select_one("a.MuiTypography-link")
        detail_link = ""
        if detail_elem and detail_elem.has_attr("href"):
            detail_link = urljoin(TARGET_URL, detail_elem["href"])  # ensure absolute URL

        cover_elem = card.select_one('img[src*="/covers/"]') or card.select_one('img[data-src*="/covers/"]')
        cover_image = ""
        if cover_elem and cover_elem.has_attr("src"):
            cover_src = cover_elem.get("src") or ""
        elif cover_elem and cover_elem.has_attr("data-src"):
            cover_src = cover_elem.get("data-src") or ""
        else:
            cover_src = ""

        if cover_src:
            cover_image = cover_src if cover_src.startswith("http") else urljoin(TARGET_URL, cover_src)

        entry = {
            "title": title,
            "description": description,
            "published_at": published_at,
            "detail_link": detail_link,
            "cover_image": cover_image,
        }

        key = detail_link or title
        if not key:
            continue

        if key in dedup:
            existing = dedup[key]
            existing_score = sum(1 for field in (existing["description"], existing["published_at"], existing["cover_image"]) if field)
            new_score = sum(1 for field in (entry["description"], entry["published_at"], entry["cover_image"]) if field)
            if new_score > existing_score:
                dedup[key] = entry
        else:
            dedup[key] = entry

    return list(dedup.values())


def fetch_books() -> List[Dict[str, str]]:
    driver = setup_driver()
    try:
        driver.get(TARGET_URL)

        wait = WebDriverWait(driver, 30)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid^="search-card"]')))

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        page_source = driver.page_source
        return parse_books(page_source)
    finally:
        driver.quit()


def save_books(books: List[Dict[str, str]], output_path: str = OUTPUT_FILE) -> None:
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(books, fp, ensure_ascii=False, indent=2)


def main() -> None:
    books = fetch_books()
    save_books(books)
    print(f"Saved {len(books)} books to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
