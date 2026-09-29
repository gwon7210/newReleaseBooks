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

    def test_missing_fields_are_none(self):
        date, sell_num = newbooks.parse_detail("<html></html>")
        self.assertIsNone(date)
        self.assertIsNone(sell_num)


class ApplyDetailsTest(unittest.TestCase):
    def test_fills_list_books_from_details(self):
        lists = {"출판사": newbooks.parse_search(SEARCH_HTML)}
        details = {
            "196521682": ("2026년 10월 01일", "500"),  # 상세 조회 성공
            "146041188": None,                          # 상세 조회 실패
        }
        newbooks.apply_details(lists, details)
        first, second = lists["출판사"]
        self.assertEqual(first["release_date"], "2026년 10월 01일")
        self.assertEqual(first["sell_num"], "500")
        self.assertEqual(second["release_date"], newbooks.NO_DATE_TEXT)
        self.assertEqual(second["sell_num"], "0")

    def test_missing_sell_num_becomes_zero_and_list_date_is_kept(self):
        lists = {"출판사": newbooks.parse_search(SEARCH_HTML, limit=1)}
        newbooks.apply_details(lists, {"196521682": (None, None)})
        book = lists["출판사"][0]
        self.assertEqual(book["release_date"], "2026년 10월 12일")
        self.assertEqual(book["sell_num"], "0")


META_HTML = """
<html><head>
<meta name="author" content="진한별 저">
<meta property="og:title" content="클로드 역대급 활용법 with 코워크, 디자인 | 진한별 | 영진닷컴 - 예스24">
<meta property="og:image" content="https://image.yes24.com/goods/195043001/xl">
</head></html>
"""


class ParseGoodsNoTest(unittest.TestCase):
    def test_accepts_urls_and_numbers(self):
        for value in (
            "https://www.yes24.com/product/goods/195043001",
            "https://www.yes24.com/Product/Goods/195043001?OzSrank=1",
            "https://m.yes24.com/goods/detail/195043001",
            "195043001",
            " 195043001 ",
            195043001,
        ):
            self.assertEqual(newbooks.parse_goods_no(value), "195043001", value)

    def test_rejects_unrecognised_values(self):
        for value in ("", None, "https://www.yes24.com/", "abc", "https://example.com/goods/x"):
            self.assertIsNone(newbooks.parse_goods_no(value), value)


class ParseBookMetaTest(unittest.TestCase):
    def test_reads_title_author_publisher(self):
        meta = newbooks.parse_book_meta(META_HTML, "195043001")
        self.assertEqual(meta["title"], "클로드 역대급 활용법 with 코워크, 디자인")
        self.assertEqual(meta["author"], "진한별 저")
        self.assertEqual(meta["publisher"], "영진닷컴")
        self.assertEqual(meta["goods_no"], "195043001")
        self.assertEqual(meta["image_url"], "https://image.yes24.com/goods/195043001/L")
        self.assertEqual(meta["detail_url"], "https://www.yes24.com/product/goods/195043001")

    def test_title_containing_separator(self):
        html = '<meta property="og:title" content="A | B 완전정복 | 홍길동 | 길벗 - 예스24">'
        meta = newbooks.parse_book_meta(html, "1")
        self.assertEqual(meta["title"], "A | B 완전정복")
        self.assertEqual(meta["publisher"], "길벗")

    def test_missing_title_returns_none(self):
        self.assertIsNone(newbooks.parse_book_meta("<html></html>", "1"))


class LoadTrackedTest(unittest.TestCase):
    def test_missing_file_is_empty(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(newbooks.load_tracked(Path(tmp) / "none.json"), [])

    def test_dedupes_and_skips_invalid(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tracked_books.json"
            path.write_text(json.dumps([
                "https://www.yes24.com/product/goods/195043001",
                "195043001",
                "not a book",
                "https://m.yes24.com/goods/detail/111",
            ]), encoding="utf-8")
            self.assertEqual(newbooks.load_tracked(path), ["195043001", "111"])


if __name__ == "__main__":
    unittest.main()
