# 신간 도서 대시보드

YES24에서 IT·컴퓨터 분야 출판사별 신간 도서를 매일 수집해 한눈에 볼 수 있는 대시보드입니다.
GitHub Actions가 하루 두 번 수집을 실행하고 GitHub Pages로 배포합니다.

## 기능

- **신간 대시보드** (`index.html`): 출판사별 최신 도서 10권. 제목, 저자, 가격, 출간일, 판매지수, 표지, NEW 배지
- **판매지수 대시보드** (`sales.html`): 판매지수 이력을 바탕으로 한 순위, 7일·30일 상승세, 도서별 추이 그래프, 출판사 비교
- 한 번 목록에 등장한 책은 최신 10권에서 밀려나도 계속 추적해 판매지수를 기록합니다
- 마지막 업데이트 시각 표시, 반응형 디자인

## 구성

| 파일 | 역할 |
| --- | --- |
| `publishers.json` | 수집 대상 출판사 목록. 이름과 YES24 출판사 번호(`mkEntrNo`) |
| `newbooks.py` | YES24 검색·상세 페이지를 requests로 조회. 수집 전체 흐름을 담당 |
| `sales_history.py` | 카탈로그·판매지수 이력 저장과 대시보드용 집계 (순수 함수) |
| `data/books.json` | 추적 도서 카탈로그. 워크플로가 매 실행 후 커밋 |
| `data/history/YYYY-MM.csv` | 날짜·도서별 판매지수 기록. 월별 파일, 워크플로가 커밋 |
| `books_data.json` | 신간 대시보드 데이터 (생성 파일, 커밋하지 않음) |
| `sales_data.json` | 판매지수 대시보드 데이터 (생성 파일, 커밋하지 않음) |
| `index.html`, `sales.html` | 정적 대시보드 페이지 |
| `.github/workflows/deploy.yml` | 테스트 → 수집 → `data/` 커밋 → `public/` 빌드 → GitHub Pages 배포 |
| `tests/` | 파서와 이력 집계 단위 테스트 |

## 판매지수 기록 방식

- 매 실행마다 카탈로그의 모든 책 상세 페이지에서 판매지수를 읽어 그날(KST) 기록으로 저장합니다. 같은 날 두 번 실행되면 나중 값이 남습니다.
- 판매지수 요소가 없는 책(예약판매 등)이나 조회에 실패한 책은 그날 기록을 남기지 않습니다. 0으로 기록되지 않습니다.
- YES24 판매지수는 최근 판매량을 반영한 가중 지수이므로, 판매가 뜸해지면 값이 내려가 변화량이 음수가 될 수 있습니다.

## 출판사 추가·삭제

`publishers.json`에 항목을 넣거나 빼면 됩니다. 출판사 번호는 YES24에서 출판사로 검색한 뒤 주소의 `mkEntrNo` 값을 사용합니다.

```json
{ "name": "영진닷컴", "id": "260" }
```

## 로컬 실행

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .   # 단위 테스트
python newbooks.py                          # 수집 (약 1분). data/와 두 JSON을 생성·갱신
python sales_history.py                     # data/만으로 sales_data.json 다시 만들기
python -m http.server 8000                  # http://localhost:8000 접속
```

로컬에서는 `deploy_info.json`이 없으므로 업데이트 시각이 "정보 없음"으로 표시됩니다.

## 라이선스

MIT License
