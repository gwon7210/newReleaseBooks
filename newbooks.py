import json
import time
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        print(f"Chrome 드라이버 초기화 실패: {e}")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

def get_publisher_books(driver, publisher_name, publisher_id):
    encoded_name = urllib.parse.quote(publisher_name)
    url = f"https://m.yes24.com/search?query={encoded_name}&domain=BOOK&viewMode=&dispNo2=001001003&mkEntrNo={publisher_id}&order=RECENT"
    
    try:
        driver.get(url)
        # 페이지가 로드될 때까지 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".itemUnit"))
        )
        
        # 잠시 대기하여 동적 콘텐츠가 로드되도록 함
        # time.sleep(1)
        
        # 페이지 소스 가져오기
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        
        books = []
        book_items = soup.select('.itemUnit')
        
        for item in book_items[:5]:  # 최대 5개 도서만 가져오기
            try:
                # 제목 선택자 수정
                title_elem = item.select_one('.info_name')
                if not title_elem:
                    continue
                title = title_elem.text.strip().replace('[도서]', '').strip()
                
                # 저자 선택자 수정
                author_elem = item.select_one('.info_auth')
                author = author_elem.text.strip() if author_elem else "저자 정보 없음"
                
                # 가격 선택자 수정
                price_elem = item.select_one('.txt_num')
                price = price_elem.text.strip() if price_elem else "가격 정보 없음"
                
                # 이미지 URL 선택자 수정
                img_elem = item.select_one('img')
                image_url = ""
                if img_elem:
                    # src 또는 data-original 속성에서 URL 가져오기
                    image_url = img_elem.get('data-original') or img_elem.get('src', '')
                    if image_url and not image_url.startswith('http'):
                        image_url = 'https:' + image_url
                    if not image_url or 'Noimg_L.jpg' in image_url:
                        image_url = 'https://image.yes24.com/momo/Noimg_L.jpg'
                
                if title:  # 제목이 있는 경우에만 추가
                    # 상품 번호 추출
                    goods_no = item.get('data-goods-no') if isinstance(item, dict) else item.attrs.get('data-goods-no', '')
                    detail_url = f"https://www.yes24.com/product/goods/{goods_no}" if goods_no else ""
                    
                    # 이미지 URL에서 상품 번호 추출 (백업 방법)
                    if not goods_no and image_url:
                        # 이미지 URL 형식: https://image.yes24.com/goods/146041188/L
                        try:
                            goods_no = image_url.split('/goods/')[1].split('/')[0]
                            detail_url = f"https://www.yes24.com/product/goods/{goods_no}"
                        except:
                            pass
                    
                    books.append({
                        'title': title,
                        'author': author,
                        'price': price,
                        'image_url': image_url,
                        'goods_no': goods_no,
                        'detail_url': detail_url
                    })
            except Exception as e:
                print(f"Error parsing book item for {publisher_name}: {e}")
                continue
        
        print(f"Found {len(books)} books for {publisher_name}")
        return books
    except Exception as e:
        print(f"Error fetching data for {publisher_name}: {e}")
        return []

def main():
    publishers = [
        {"name": "골든래빗", "id": "287363"},
        {"name": "한빛미디어", "id": "1469"},
        # {"name": "인사이트", "id": "289113"},
        # {"name": "리코멘드", "id": "314006"},
        # {"name": "길벗", "id": "231"},
        # {"name": "길벗캠퍼스", "id": "303742"},
        # {"name": "책만", "id": "297319"},
        # {"name": "프리렉", "id": "10755"},
        # {"name": "이지스퍼블리싱", "id": "117983"},
        # {"name": "제이펍", "id": "107878"},
        # {"name": "위키북스", "id": "120040"},
        # {"name": "시프트", "id": "327076"},
        # {"name": "루비페이퍼", "id": "183510"},
        # {"name": "에이콘출판사", "id": "7813"},
        # {"name": "에이콘온", "id": "332424"},
        # {"name": "정보문화사", "id": "1"},
        # {"name": "스마트북스", "id": "132231"},
        # {"name": "비제이퍼블릭", "id": "108933"}
    ]
    
    driver = setup_driver()
    try:
                # WebDriver 웜업
        print("Warming up WebDriver...")
        driver.get("https://m.yes24.com")
        time.sleep(5)  # 웜업을 위한 대기 시간

        
        all_data = {}
        for publisher in publishers:
            print(f"Fetching data for {publisher['name']}...")
            books = get_publisher_books(driver, publisher["name"], publisher["id"])
            all_data[publisher["name"]] = books
            time.sleep(0.1)  # 요청 간 2초 대기
        
        # JSON 파일로 저장
        with open('books_data.json', 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        
        print("Data collection completed!")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
