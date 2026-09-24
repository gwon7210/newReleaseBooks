# 신간 도서 대시보드

YES24에서 IT·컴퓨터 분야 출판사별 신간 도서를 매일 수집해 한눈에 볼 수 있는 대시보드입니다.
GitHub Actions가 하루 두 번 수집을 실행하고 GitHub Pages로 배포합니다.

## 기능

- 출판사별 최신 도서 10권 표시 (제목, 저자, 가격, 출간일, 판매지수, 표지)
- NEW 배지 (출간일이 최근이거나 출간 예정인 도서)
- 마지막 업데이트 시각 표시
- 반응형 디자인

## 구성

| 파일 | 역할 |
| --- | --- |
| `publishers.json` | 수집 대상 출판사 목록. 이름과 YES24 출판사 번호(`mkEntrNo`) |
| `newbooks.py` | YES24 모바일 검색과 상세 페이지를 requests로 조회해 `books_data.json` 생성 |
| `index.html` | `books_data.json`과 `deploy_info.json`을 읽어 렌더링하는 정적 페이지 |
| `.github/workflows/deploy.yml` | 수집 후 `public/`에 페이지와 데이터를 모아 GitHub Pages로 배포 |
| `tests/` | 파서 단위 테스트 |

## 출판사 추가·삭제

`publishers.json`에 항목을 넣거나 빼면 됩니다. 출판사 번호는 YES24에서 출판사로 검색한 뒤 주소의 `mkEntrNo` 값을 사용합니다.

```json
{ "name": "영진닷컴", "id": "260" }
```

## 로컬 실행

```bash
pip install -r requirements.txt
python newbooks.py                 # books_data.json 생성 (1~2분)
python -m unittest tests.test_newbooks
python -m http.server 8000         # http://localhost:8000 접속
```

로컬에서는 `deploy_info.json`이 없으므로 업데이트 시각이 "정보 없음"으로 표시됩니다.

## 라이선스

MIT License
