"""판매지수 이력 저장과 판매 대시보드용 집계.

- data/books.json        : 한 번이라도 목록에 등장한 도서 카탈로그 (goods_no 키)
- data/history/YYYY-MM.csv : (KST 날짜, 도서)당 한 행의 판매지수 기록, 월별 샤드
- sales_data.json        : sales.html이 읽는 집계 산출물 (배포용, 커밋하지 않음)

네트워크 접근 없이 파일과 순수 함수만 다룬다.
`python sales_history.py`로 data/에서 sales_data.json을 다시 만들 수 있다.
"""

import csv
import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path("data")
CATALOG_FILE = DATA_DIR / "books.json"
HISTORY_DIR = DATA_DIR / "history"
SALES_DATA_FILE = Path("sales_data.json")
PUBLISHERS_FILE = Path("publishers.json")

SERIES_DAYS = 90        # sales_data.json에 담는 추이 길이 (오늘 기준 달력 일수)
NEW_RELEASE_DAYS = 30   # 출간 후 이 일수 안이면 신간으로 분류
KST = timezone(timedelta(hours=9))

_KOREAN_DATE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")
_CATALOG_FIELDS_FROM_LIST = ("title", "author", "image_url", "detail_url")


# --------------------------------------------------------------------------- #
# 날짜
# --------------------------------------------------------------------------- #
def kst_today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def release_date_iso(text: str | None) -> str | None:
    """'2026년 09월 21일' -> '2026-09-21'. 형식이 다르면 None."""
    if not text:
        return None
    match = _KOREAN_DATE.search(text)
    if not match:
        return None
    year, month, day = (int(g) for g in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def _parse(day: str) -> date:
    return date.fromisoformat(day)


def _shift(day: str, days: int) -> str:
    return (_parse(day) + timedelta(days=days)).isoformat()


# --------------------------------------------------------------------------- #
# 카탈로그
# --------------------------------------------------------------------------- #
def load_catalog(path: Path = CATALOG_FILE) -> dict[str, dict]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_catalog(path: Path, catalog: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def merge_catalog(catalog: dict[str, dict], lists: dict[str, list[dict]], today: str) -> dict[str, dict]:
    """오늘 수집한 출판사별 목록을 카탈로그에 반영한다.

    처음 보는 책은 새 항목으로 넣고, 이미 있는 책은 표시 정보와 last_seen만 갱신한다.
    publisher는 처음 등장한 출판사로 고정된다.
    """
    for publisher, books in lists.items():
        for book in books:
            goods_no = book.get("goods_no")
            if not goods_no:
                continue
            entry = catalog.get(goods_no)
            if entry is None:
                catalog[goods_no] = {
                    **{field: book.get(field, "") for field in _CATALOG_FIELDS_FROM_LIST},
                    "publisher": publisher,
                    "release_date": book.get("release_date"),
                    "first_seen": today,
                    "last_seen": today,
                }
                continue
            for field in _CATALOG_FIELDS_FROM_LIST:
                if book.get(field):
                    entry[field] = book[field]
            if not entry.get("release_date") and book.get("release_date"):
                entry["release_date"] = book["release_date"]
            entry["last_seen"] = today
    return catalog


def apply_release_dates(catalog: dict[str, dict], details: dict[str, tuple | None]) -> None:
    """상세 페이지에서 얻은 출간일을 카탈로그에 반영한다. 조회 실패(None)는 건너뛴다."""
    for goods_no, result in details.items():
        if result and result[0] and goods_no in catalog:
            catalog[goods_no]["release_date"] = result[0]


# --------------------------------------------------------------------------- #
# 이력 (월별 CSV 샤드)
# --------------------------------------------------------------------------- #
def month_file(history_dir: Path, day: str) -> Path:
    return history_dir / f"{day[:7]}.csv"


def _read_rows(path: Path) -> list[tuple[str, str, int]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fp:
        reader = csv.reader(fp)
        next(reader, None)  # header
        return [(row[0], row[1], int(row[2])) for row in reader if len(row) == 3]


def load_history(history_dir: Path = HISTORY_DIR) -> dict[str, list[tuple[str, int]]]:
    """goods_no -> [(date, sell_num), ...] 날짜 오름차순."""
    history: dict[str, list[tuple[str, int]]] = defaultdict(list)
    if not history_dir.exists():
        return {}
    for path in sorted(history_dir.glob("*.csv")):
        for day, goods_no, value in _read_rows(path):
            history[goods_no].append((day, value))
    for points in history.values():
        points.sort()
    return dict(history)


def upsert_day(history_dir: Path, day: str, values: dict[str, int]) -> int:
    """해당 날짜의 기록을 통째로 교체한다. 당월 샤드 파일만 다시 쓴다."""
    history_dir.mkdir(parents=True, exist_ok=True)
    path = month_file(history_dir, day)
    rows = [row for row in _read_rows(path) if row[0] != day]
    rows.extend((day, goods_no, int(value)) for goods_no, value in values.items())
    rows.sort()
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp, lineterminator="\n")
        writer.writerow(["date", "goods_no", "sell_num"])
        writer.writerows(rows)
    return len(values)


# --------------------------------------------------------------------------- #
# 집계
# --------------------------------------------------------------------------- #
def value_on_or_before(points: list[tuple[str, int]], target: str) -> tuple[str, int] | None:
    for point in reversed(points):
        if point[0] <= target:
            return point
    return None


def compute_delta(points: list[tuple[str, int]], days: int) -> tuple[int | None, int | None]:
    """최근 값과 `days`일 전(또는 그 이전 가장 가까운 날) 값의 차이와 실제 기준 일수.

    기준일보다 오래된 기록이 없으면 가장 오래된 기록을 기준으로 삼는다.
    이때 반환되는 일수가 `days`보다 작아 부분 데이터임을 알 수 있다.
    """
    if len(points) < 2:
        return None, None
    latest_day, latest = points[-1]
    base = value_on_or_before(points, _shift(latest_day, -days)) or points[0]
    span = (_parse(latest_day) - _parse(base[0])).days
    if span <= 0:
        return None, None
    return latest - base[1], span


def is_new_release(entry: dict, today: str) -> bool:
    anchor = entry.get("release_date") or entry.get("first_seen")
    return bool(anchor) and anchor >= _shift(today, -NEW_RELEASE_DAYS)


def build_book_entry(goods_no: str, meta: dict, points: list[tuple[str, int]], dates: list[str]) -> dict:
    entry = {
        "goods_no": goods_no,
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "publisher": meta.get("publisher", ""),
        "image_url": meta.get("image_url", ""),
        "detail_url": meta.get("detail_url", ""),
        "release_date": release_date_iso(meta.get("release_date")),
        "first_seen": meta.get("first_seen"),
        "last_seen": meta.get("last_seen"),
        "latest": None,
        "latest_date": None,
        "delta1": None,
        "delta1_days": None,
        "delta3": None,
        "delta3_days": None,
        "delta7": None,
        "delta7_days": None,
        "delta30": None,
        "delta30_days": None,
    }
    if not points:
        return entry

    entry["latest_date"], entry["latest"] = points[-1]
    entry["delta1"], entry["delta1_days"] = compute_delta(points, 1)
    entry["delta3"], entry["delta3_days"] = compute_delta(points, 3)
    entry["delta7"], entry["delta7_days"] = compute_delta(points, 7)
    entry["delta30"], entry["delta30_days"] = compute_delta(points, 30)

    index = {day: i for i, day in enumerate(dates)}
    in_window = [(index[day], value) for day, value in points if day in index]
    if in_window:
        start = in_window[0][0]
        series: list[int | None] = [None] * (len(dates) - start)
        for i, value in in_window:
            series[i - start] = value
        entry["series_start"] = start
        entry["series"] = series
    return entry


def _avg(values: list[int]) -> int | None:
    return round(sum(values) / len(values)) if values else None


def build_publisher_stats(books: list[dict], publisher_order: list[str], today: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for book in books:
        grouped[book["publisher"]].append(book)

    names = list(publisher_order) + sorted(name for name in grouped if name not in publisher_order)
    stats = []
    for name in names:
        ranked = [b for b in grouped.get(name, []) if b["latest"] is not None]
        new = [b for b in ranked if is_new_release(b, today)]
        top = max(ranked, key=lambda b: b["latest"], default=None)
        stats.append(
            {
                "name": name,
                "book_count": len(ranked),
                "total": sum(b["latest"] for b in ranked),
                "avg": _avg([b["latest"] for b in ranked]),
                "delta7": sum(b["delta7"] for b in ranked if b["delta7"] is not None),
                "delta30": sum(b["delta30"] for b in ranked if b["delta30"] is not None),
                "new_count": len(new),
                "new_avg": _avg([b["latest"] for b in new]),
                "new_delta7": sum(b["delta7"] for b in new if b["delta7"] is not None),
                "top_goods_no": top["goods_no"] if top else None,
            }
        )
    return stats


def build_sales_data(
    catalog: dict[str, dict],
    history: dict[str, list[tuple[str, int]]],
    today: str,
    publisher_order: list[str],
    series_days: int = SERIES_DAYS,
) -> dict:
    window_start = _shift(today, -(series_days - 1))
    dates = sorted({day for points in history.values() for day, _ in points if day >= window_start})

    books = [
        build_book_entry(goods_no, meta, history.get(goods_no, []), dates)
        for goods_no, meta in catalog.items()
    ]
    books.sort(key=lambda b: (b["latest"] is None, -(b["latest"] or 0), b["title"]))

    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "today": today,
        "latest_date": dates[-1] if dates else None,
        "dates": dates,
        "books": books,
        "publishers": build_publisher_stats(books, publisher_order, today),
    }


def publisher_order_from_file(path: Path = PUBLISHERS_FILE) -> list[str]:
    if not path.exists():
        return []
    return [p["name"] for p in json.loads(path.read_text(encoding="utf-8"))]


def rebuild(today: str | None = None) -> dict:
    """data/ 디렉터리에서 sales_data.json을 다시 만든다."""
    data = build_sales_data(
        load_catalog(CATALOG_FILE),
        load_history(HISTORY_DIR),
        today or kst_today(),
        publisher_order_from_file(),
    )
    SALES_DATA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{SALES_DATA_FILE}: 도서 {len(data['books'])}권, 기록 일수 {len(data['dates'])}일")
    return data


if __name__ == "__main__":
    rebuild()
