"""로컬 미리보기용 샘플 판매지수 데이터 생성.

data/의 실제 카탈로그와 오늘 판매지수를 기준으로 과거 며칠치 이력을 무작위로 지어내
sales_data.json만 다시 쓴다. data/는 건드리지 않으며, 실제 데이터로 되돌리려면
`python sales_history.py`를 실행하면 된다.

사용법:
    python sample_data.py            # 40일치
    python sample_data.py --days 90  # 90일치
"""

import argparse
import json
import random
from datetime import timedelta

import sales_history as sh


def synthesize(history: dict[str, list[tuple[str, int]]], today: str, days: int, seed: int) -> dict:
    """책마다 다른 추세로 `days`일치 이력을 만든다. 마지막 값은 실제 오늘 값이다."""
    rng = random.Random(seed)
    end = sh._parse(today)
    fake: dict[str, list[tuple[str, int]]] = {}
    for goods_no, points in history.items():
        latest = points[-1][1]
        # 추적 시작 시점을 섞어 신간(짧은 이력)과 구간(긴 이력)이 같이 나오게 한다.
        # 0이면 오늘 처음 들어온 책(기록 하루)이다.
        span = rng.choice([days, days, days, days, days // 2, 10, 3, 0])
        slope = rng.uniform(-0.015, 0.02)         # 하루당 변화율 (음수면 내려가는 추세). 40일 기준 최대 80% 변동
        series = []
        for back in range(span, -1, -1):
            if back and rng.random() < 0.04:      # 가끔 결측(조회 실패)
                continue
            day = (end - timedelta(days=back)).isoformat()
            value = latest * (1 - slope * back) * (1 + rng.uniform(-0.02, 0.02))
            series.append((day, max(0, int(value)) if back else latest))
        fake[goods_no] = series
    return fake


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=40, help="만들 이력 일수 (기본 40)")
    parser.add_argument("--seed", type=int, default=1, help="난수 시드")
    args = parser.parse_args()

    catalog = sh.load_catalog(sh.CATALOG_FILE)
    history = sh.load_history(sh.HISTORY_DIR)
    if not catalog or not history:
        raise SystemExit("data/에 실제 수집 결과가 없습니다. 먼저 python newbooks.py 를 실행하세요.")

    today = max(day for points in history.values() for day, _ in points)
    fake_history = synthesize(history, today, args.days, args.seed)

    # 신간 판정이 섞이도록 first_seen도 이력 시작일에 맞춘다 (메모리에서만)
    for goods_no, points in fake_history.items():
        if goods_no in catalog:
            catalog[goods_no]["first_seen"] = points[0][0]

    data = sh.build_sales_data(catalog, fake_history, today, sh.publisher_order_from_file())
    sh.SALES_DATA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fresh = sum(1 for b in data["books"] if b["first_seen"] == today)
    print(f"{sh.SALES_DATA_FILE}: 샘플 {len(data['dates'])}일치, 도서 {len(data['books'])}권, 오늘 신규 {fresh}권 "
          f"(실제 데이터로 되돌리기: python sales_history.py)")


if __name__ == "__main__":
    main()
