"""YES24 출판사별 신간 수집기.

publishers.json에 적힌 출판사마다 YES24 모바일 검색(최신순)을 조회해
도서 목록을 만들고, 각 도서의 상세 페이지에서 출간일과 판매지수를 보강한 뒤
books_data.json으로 저장한다. 브라우저 없이 requests만 사용한다.
"""

import json
import re
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://m.yes24.com"
PUBLISHERS_FILE = Path("publishers.json")
OUTPUT_FILE = Path("books_data.json")
NO_IMAGE_URL = "https://image.yes24.com/momo/Noimg_L.jpg"
NO_DATE_TEXT = "출간일 정보 없음"

MAX_BOOKS_PER_PUBLISHER = 10
MAX_WORKERS = 8
RETRIES = 3
RETRY_WAIT_SECONDS = 2
TIMEOUT_SECONDS = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

_DOTTED_DATE = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.?")
_GOODS_IN_PATH = re.compile(r"/goods/(?:detail/)?(\d+)")

_thread_local = threading.local()


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def new_session() -> requests.Session:
    """헤더가 설정된 세션을 만들고 홈을 한 번 방문해 쿠키를 받아 둔다.

    검색 페이지는 세션 쿠키가 없으면 홈으로 리다이렉트된다.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    session.get(BASE_URL, timeout=TIMEOUT_SECONDS)
    return session


def thread_session() -> requests.Session:
    """스레드마다 하나씩 세션을 재사용한다."""
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = new_session()
        _thread_local.session = session
    return session


def fetch(session: requests.Session, url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            print(f"  요청 실패 ({attempt}/{RETRIES}) {url}: {exc}")
            if attempt < RETRIES:
                time.sleep(RETRY_WAIT_SECONDS * attempt)
    raise RuntimeError(f"{RETRIES}회 재시도 후에도 실패: {url}") from last_error


# --------------------------------------------------------------------------- #
# 파싱
# --------------------------------------------------------------------------- #
def normalize_date(text: str | None) -> str | None:
    """'2025.05.13.' 형태를 대시보드가 읽는 '2025년 05월 13일'로 맞춘다."""
    if not text:
        return None
    text = text.strip()
    match = _DOTTED_DATE.fullmatch(text)
    if match:
        year, month, day = match.groups()
        return f"{year}년 {int(month):02d}월 {int(day):02d}일"
    return text


def _text(node, selector: str) -> str | None:
    found = node.select_one(selector)
    return found.get_text(strip=True) if found else None


def _image_url(item) -> str:
    img = item.select_one("img")
    if not img:
        return NO_IMAGE_URL
    url = img.get("data-original") or img.get("src") or ""
    if url and not url.startswith("http"):
        url = "https:" + url
    if not url or "Noimg_L.jpg" in url:
        return NO_IMAGE_URL
    return url


def _goods_no(item, image_url: str) -> str:
    for link in item.select("a[href]"):
        match = _GOODS_IN_PATH.search(link["href"])
        if match:
            return match.group(1)
    match = _GOODS_IN_PATH.search(image_url)
    return match.group(1) if match else ""


def parse_search(html: str, limit: int = MAX_BOOKS_PER_PUBLISHER) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for item in soup.select(".itemUnit"):
        title = _text(item, ".info_name")
        if not title:
            continue
        title = title.replace("[도서]", "").strip()
        image_url = _image_url(item)
        goods_no = _goods_no(item, image_url)
        books.append(
            {
                "title": title,
                "author": _text(item, ".info_auth") or "저자 정보 없음",
                "price": _text(item, ".txt_num") or "가격 정보 없음",
                "image_url": image_url,
                "goods_no": goods_no,
                "detail_url": f"https://www.yes24.com/product/goods/{goods_no}" if goods_no else "",
                "release_date": normalize_date(_text(item, ".info_date")),
                "sell_num": "0",
            }
        )
        if len(books) >= limit:
            break
    return books


def parse_detail(html: str) -> tuple[str | None, str]:
    """상세 페이지에서 (출간일, 판매지수)를 꺼낸다. 판매지수는 숫자만 남긴다."""
    soup = BeautifulSoup(html, "html.parser")
    date = normalize_date(_text(soup, ".authPub .date") or _text(soup, ".gd_date"))
    sell_text = _text(soup, ".gdBasicSet.gdRating .sellNum .num") or _text(soup, ".gd_sellNum") or ""
    digits = re.sub(r"\D", "", sell_text)
    return date, digits or "0"


# --------------------------------------------------------------------------- #
# 수집
# --------------------------------------------------------------------------- #
def search_url(publisher: dict) -> str:
    query = urllib.parse.urlencode(
        {
            "query": publisher["name"],
            "domain": "BOOK",
            "viewMode": "",
            "dispNo2": "001001003",  # 컴퓨터/IT 카테고리
            "mkEntrNo": publisher["id"],
            "order": "RECENT",
        }
    )
    return f"{BASE_URL}/search?{query}"


def fetch_publisher_books(publisher: dict) -> tuple[str, list[dict]]:
    name = publisher["name"]
    try:
        books = parse_search(fetch(thread_session(), search_url(publisher)))
        print(f"{name}: {len(books)}권")
    except Exception as exc:  # 한 출판사 실패가 전체를 막지 않도록
        print(f"{name}: 목록 조회 실패 - {exc}")
        books = []
    return name, books


def enrich_book(book: dict) -> dict:
    if not book["goods_no"]:
        book["release_date"] = book["release_date"] or NO_DATE_TEXT
        return book
    try:
        date, sell_num = parse_detail(
            fetch(thread_session(), f"{BASE_URL}/goods/detail/{book['goods_no']}")
        )
        book["release_date"] = date or book["release_date"] or NO_DATE_TEXT
        book["sell_num"] = sell_num
    except Exception as exc:
        print(f"  상세 조회 실패 {book['goods_no']}: {exc}")
        book["release_date"] = book["release_date"] or NO_DATE_TEXT
    return book


def collect(publishers: list[dict]) -> dict[str, list[dict]]:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = dict(pool.map(fetch_publisher_books, publishers))
        all_books = [book for books in results.values() for book in books]
        print(f"상세 페이지 {len(all_books)}건 조회 중...")
        list(pool.map(enrich_book, all_books))
    return results


def main() -> int:
    publishers = json.loads(PUBLISHERS_FILE.read_text(encoding="utf-8"))
    started = time.time()
    data = collect(publishers)
    OUTPUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    total = sum(len(v) for v in data.values())
    empty = [name for name, books in data.items() if not books]
    print(f"완료: {len(data)}개 출판사, {total}권, {time.time() - started:.0f}초 -> {OUTPUT_FILE}")
    if empty:
        print(f"도서가 없는 출판사 {len(empty)}곳: {', '.join(empty)}")
    if total == 0:
        print("수집된 도서가 없습니다. 사이트 구조가 바뀌었는지 확인하세요.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
