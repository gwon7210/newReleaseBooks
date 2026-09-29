"""YES24 출판사별 신간 수집기 + 판매지수 기록.

1. publishers.json의 출판사마다 YES24 모바일 검색(최신순)으로 최신 도서 목록을 받는다.
2. 목록을 data/books.json 카탈로그에 합친다. 한 번 등장한 책은 계속 추적 대상이다.
   tracked_books.json에 직접 적어 둔 책도 카탈로그에 등록한다.
3. 카탈로그의 모든 책 상세 페이지에서 출간일과 판매지수를 병렬로 조회한다.
4. books_data.json(신간 대시보드), data/history/(판매지수 이력), sales_data.json(판매 대시보드)을 쓴다.

브라우저 없이 requests만 사용한다.
"""

import json
import re
import sys
import threading
import time
import urllib.parse
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

import sales_history as sh

BASE_URL = "https://m.yes24.com"
PUBLISHERS_FILE = Path("publishers.json")
TRACKED_FILE = Path("tracked_books.json")   # 출판사 목록과 무관하게 직접 추적할 책 (YES24 주소 또는 상품 번호)
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
_GOODS_IN_PATH = re.compile(r"/goods/(?:detail/)?(\d+)", re.IGNORECASE)
_YES24_HOST = re.compile(r"^https?://([a-z0-9-]+\.)*yes24\.com/", re.IGNORECASE)
_OG_TITLE_SUFFIX = " - 예스24"

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
            status = getattr(exc.response, "status_code", None)
            if status is not None and 400 <= status < 500:
                # 없는 상품(404) 등은 재시도해도 결과가 같다
                raise RuntimeError(f"HTTP {status}: {url}") from exc
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


def parse_goods_no(value) -> str | None:
    """YES24 상품 주소나 상품 번호에서 번호만 꺼낸다. 알아볼 수 없으면 None."""
    if value is None:
        return None
    text = str(value).strip()
    if text.isdigit():
        return text
    if not _YES24_HOST.match(text):
        return None
    match = _GOODS_IN_PATH.search(text)
    return match.group(1) if match else None


def _meta_content(soup, **attrs) -> str | None:
    tag = soup.find("meta", attrs=attrs)
    content = tag.get("content") if tag else None
    return content.strip() if content else None


def parse_book_meta(html: str, goods_no: str) -> dict | None:
    """상세 페이지에서 카탈로그 등록에 필요한 제목·저자·출판사를 꺼낸다.

    og:title은 "제목 | 저자 | 출판사 - 예스24" 형식이다. 제목에 " | "가 들어 있을 수 있어 뒤에서부터 나눈다.
    """
    soup = BeautifulSoup(html, "html.parser")
    og_title = _meta_content(soup, property="og:title")
    if not og_title:
        return None
    parts = og_title.removesuffix(_OG_TITLE_SUFFIX).rsplit(" | ", 2)
    if len(parts) != 3 or not parts[0].strip():
        return None
    title, author, publisher = (part.strip() for part in parts)
    return {
        "goods_no": goods_no,
        "title": title,
        "author": _meta_content(soup, name="author") or author,
        "publisher": publisher,
        "image_url": f"https://image.yes24.com/goods/{goods_no}/L",
        "detail_url": f"https://www.yes24.com/product/goods/{goods_no}",
    }


def parse_detail(html: str) -> tuple[str | None, str | None]:
    """상세 페이지에서 (출간일, 판매지수)를 꺼낸다.

    판매지수는 숫자만 남긴다. 요소 자체가 없으면(예약판매, 마크업 변경) None을 돌려주어
    "0"으로 기록되는 일을 막는다.
    """
    soup = BeautifulSoup(html, "html.parser")
    date = normalize_date(_text(soup, ".authPub .date") or _text(soup, ".gd_date"))
    sell_text = _text(soup, ".gdBasicSet.gdRating .sellNum .num") or _text(soup, ".gd_sellNum")
    if sell_text is None:
        return date, None
    return date, re.sub(r"\D", "", sell_text) or "0"


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


def collect_lists(publishers: list[dict]) -> dict[str, list[dict]]:
    """출판사별 최신 도서 목록. {출판사명: [도서, ...]} (publishers.json 순서 유지)"""
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        return dict(pool.map(fetch_publisher_books, publishers))


def fetch_detail(goods_no: str) -> tuple[str | None, str | None] | None:
    """상세 페이지의 (출간일, 판매지수). 요청 실패는 None."""
    try:
        return parse_detail(fetch(thread_session(), f"{BASE_URL}/goods/detail/{goods_no}"))
    except Exception as exc:
        print(f"  상세 조회 실패 {goods_no}: {exc}")
        return None


def fetch_details(goods_nos: Iterable[str]) -> dict[str, tuple[str | None, str | None] | None]:
    targets = sorted(set(goods_nos))
    print(f"상세 페이지 {len(targets)}건 조회 중...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = dict(zip(targets, pool.map(fetch_detail, targets)))
    ok = sum(1 for r in results.values() if r is not None)
    print(f"상세 조회 성공 {ok}/{len(targets)}")
    if targets and ok < len(targets) / 2:
        print("경고: 상세 조회 성공률이 50% 미만입니다. 차단 또는 사이트 구조 변경을 확인하세요.")
    return results


def load_tracked(path: Path = TRACKED_FILE) -> list[str]:
    """tracked_books.json의 상품 번호 목록. 중복은 하나로, 알아볼 수 없는 항목은 건너뛴다."""
    if not path.exists():
        return []
    goods_nos: list[str] = []
    for entry in json.loads(path.read_text(encoding="utf-8")):
        goods_no = parse_goods_no(entry)
        if goods_no is None:
            print(f"  {path.name}: 알 수 없는 항목을 건너뜁니다 - {entry!r}")
        elif goods_no not in goods_nos:
            goods_nos.append(goods_no)
    return goods_nos


def register_tracked(catalog: dict[str, dict], goods_nos: list[str], today: str) -> int:
    """직접 지정한 책 중 카탈로그에 없는 것을 등록한다. 등록한 권수를 돌려준다."""
    added = 0
    for goods_no in goods_nos:
        if goods_no in catalog:
            continue
        try:
            meta = parse_book_meta(fetch(thread_session(), f"{BASE_URL}/goods/detail/{goods_no}"), goods_no)
        except Exception as exc:
            print(f"  직접 지정 도서 {goods_no}: 조회 실패 - {exc}")
            continue
        if meta is None:
            print(f"  직접 지정 도서 {goods_no}: 제목을 읽지 못해 건너뜁니다")
            continue
        if sh.add_tracked_book(catalog, meta, today):
            added += 1
            print(f"  직접 지정 도서 등록: {meta['title']} ({meta['publisher']})")
    return added


def apply_details(lists: dict[str, list[dict]], details: dict[str, tuple | None]) -> None:
    """목록 도서에 상세 조회 결과를 반영한다. books_data.json 형식은 예전과 같다."""
    for books in lists.values():
        for book in books:
            result = details.get(book["goods_no"]) if book["goods_no"] else None
            date, sell_num = result if result else (None, None)
            book["release_date"] = date or book["release_date"] or NO_DATE_TEXT
            book["sell_num"] = sell_num if sell_num is not None else "0"


def main() -> int:
    publishers = json.loads(PUBLISHERS_FILE.read_text(encoding="utf-8"))
    today = sh.kst_today()
    started = time.time()

    lists = collect_lists(publishers)
    listed = sum(len(v) for v in lists.values())
    if listed == 0:
        print("수집된 도서가 없습니다. 사이트 구조가 바뀌었는지 확인하세요.")
        return 1

    catalog = sh.load_catalog(sh.CATALOG_FILE)
    sh.merge_catalog(catalog, lists, today)
    register_tracked(catalog, load_tracked(), today)

    details = fetch_details(catalog.keys())

    apply_details(lists, details)
    OUTPUT_FILE.write_text(json.dumps(lists, ensure_ascii=False, indent=2), encoding="utf-8")

    sh.apply_release_dates(catalog, details)
    sh.save_catalog(sh.CATALOG_FILE, catalog)

    values = {g: int(r[1]) for g, r in details.items() if r and r[1] is not None}
    rows = sh.upsert_day(sh.HISTORY_DIR, today, values)

    sales = sh.build_sales_data(catalog, sh.load_history(sh.HISTORY_DIR), today, [p["name"] for p in publishers])
    sh.SALES_DATA_FILE.write_text(json.dumps(sales, ensure_ascii=False), encoding="utf-8")

    empty = [name for name, books in lists.items() if not books]
    print(
        f"완료: 출판사 {len(lists)}곳, 목록 {listed}권, 추적 {len(catalog)}권, "
        f"오늘 기록 {rows}행, 기록 일수 {len(sales['dates'])}일, {time.time() - started:.0f}초"
    )
    if empty:
        print(f"도서가 없는 출판사 {len(empty)}곳: {', '.join(empty)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
