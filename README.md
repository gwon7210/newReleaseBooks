# newReleaseBooks

IT 출판사들의 최신 도서 정보를 수집하고 대시보드로 보여주는 프로젝트입니다.

## 기능

- 주요 IT 출판사들의 최신 도서 정보 수집
- 도서 제목, 저자, 가격, 이미지 URL 정보 제공
- 웹 대시보드를 통한 시각화

## 기술 스택

- Python 3.x
- Selenium
- BeautifulSoup4
- Requests
- HTML/CSS/JavaScript

## 설치 방법

1. 저장소 클론
```bash
git clone https://github.com/yourusername/newReleaseBooks.git
cd newReleaseBooks
```

2. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

3. Chrome 브라우저 설치
- [Chrome 브라우저](https://www.google.com/chrome/)를 설치해주세요.

## 사용 방법

1. 도서 데이터 수집
```bash
python newbooks.py
```

2. 웹 서버 실행
```bash
python -m http.server 8000
```

3. 웹 브라우저에서 `http://localhost:8000/dashboard.html` 접속

## 수집하는 출판사

- 한빛미디어
- 골든래빗
- 인사이트
- 리코멘드
- 길벗
- 길벗캠퍼스
- 책만
- 프리렉
- 이지스퍼블리싱
- 제이펍
- 위키북스
- 시프트
- 루비페이퍼
- 에이콘출판사
- 에이콘온
- 정보문화사
- 스마트북스
- 비제이퍼블릭

## 라이선스

MIT License
