# 신간 도서 대시보드

출판사별 신간 도서를 한눈에 볼 수 있는 대시보드입니다.

## 기능

- 출판사별 신간 도서 목록 표시
- 도서 정보 (제목, 저자, 가격, 출간일, 판매지수)
- NEW 배지 (출간일로부터 7일 이내)
- 반응형 디자인

## 기술 스택

- Python
- Selenium
- BeautifulSoup4
- HTML/CSS/JavaScript

## 설치 및 실행

1. 필요한 패키지 설치:
```bash
pip install -r requirements.txt
```

2. 데이터 수집:
```bash
python newbooks.py
```

3. 웹 서버 실행:
```bash
python -m http.server 8000
```

4. 브라우저에서 `http://localhost:8000` 접속

## 라이선스

MIT License
