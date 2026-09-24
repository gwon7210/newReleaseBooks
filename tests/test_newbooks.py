import unittest

import newbooks


SEARCH_HTML = """
<div class="itemUnit">
  <a href="/goods/detail/196521682"><img data-original="//image.yes24.com/goods/196521682/L" src="//image.yes24.com/momo/Noimg_L.jpg"></a>
  <div class="info_name">[도서]2027 이기적 SQLD</div>
  <div class="info_auth">강태우저</div>
  <span class="txt_num">22,500원</span>
  <span class="authPub info_date">2026.10.12.</span>
</div>
<div class="itemUnit">
  <a href="/goods/detail/146041188"><img src="https://image.yes24.com/goods/146041188/L"></a>
  <div class="info_name">나노바나나 디자인 아이디어북</div>
  <div class="info_auth">홍길동저</div>
  <span class="txt_num">18,000원</span>
</div>
<div class="itemUnit">
  <div class="info_auth">제목 없는 항목</div>
</div>
"""

DETAIL_HTML = """
<div class="authPub"><span class="date">2025.05.13.</span></div>
<div class="gdBasicSet gdRating"><span class="sellNum">판매지수 <em class="num">1,128</em></span></div>
"""


class NormalizeDateTest(unittest.TestCase):
    def test_dotted_date_becomes_korean(self):
        self.assertEqual(newbooks.normalize_date("2025.05.13."), "2025년 05월 13일")

    def test_korean_date_is_unchanged(self):
        self.assertEqual(newbooks.normalize_date("2025년 05월 13일"), "2025년 05월 13일")

    def test_empty_returns_none(self):
        self.assertIsNone(newbooks.normalize_date(""))
        self.assertIsNone(newbooks.normalize_date(None))


class ParseSearchTest(unittest.TestCase):
    def setUp(self):
        self.books = newbooks.parse_search(SEARCH_HTML)

    def test_skips_items_without_title(self):
        self.assertEqual(len(self.books), 2)

    def test_first_book_fields(self):
        book = self.books[0]
        self.assertEqual(book["title"], "2027 이기적 SQLD")
        self.assertEqual(book["author"], "강태우저")
        self.assertEqual(book["price"], "22,500원")
        self.assertEqual(book["goods_no"], "196521682")
        self.assertEqual(book["detail_url"], "https://www.yes24.com/product/goods/196521682")
        self.assertEqual(book["image_url"], "https://image.yes24.com/goods/196521682/L")
        self.assertEqual(book["release_date"], "2026년 10월 12일")

    def test_missing_date_is_none(self):
        self.assertIsNone(self.books[1]["release_date"])

    def test_goods_no_from_image_when_no_link(self):
        html = '<div class="itemUnit"><img src="https://image.yes24.com/goods/999/L"><div class="info_name">x</div></div>'
        book = newbooks.parse_search(html)[0]
        self.assertEqual(book["goods_no"], "999")

    def test_limit(self):
        self.assertEqual(len(newbooks.parse_search(SEARCH_HTML, limit=1)), 1)


class ParseDetailTest(unittest.TestCase):
    def test_extracts_date_and_sell_num(self):
        date, sell_num = newbooks.parse_detail(DETAIL_HTML)
        self.assertEqual(date, "2025년 05월 13일")
        self.assertEqual(sell_num, "1128")

    def test_missing_fields(self):
        date, sell_num = newbooks.parse_detail("<html></html>")
        self.assertIsNone(date)
        self.assertEqual(sell_num, "0")


if __name__ == "__main__":
    unittest.main()
