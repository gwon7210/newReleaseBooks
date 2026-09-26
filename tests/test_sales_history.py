import tempfile
import unittest
from pathlib import Path

import sales_history as sh


def book(goods_no, title="제목", release_date=None):
    return {
        "title": title,
        "author": "저자",
        "price": "10,000원",
        "image_url": f"https://image.yes24.com/goods/{goods_no}/L",
        "goods_no": goods_no,
        "detail_url": f"https://www.yes24.com/product/goods/{goods_no}",
        "release_date": release_date,
        "sell_num": "0",
    }


class ReleaseDateIsoTest(unittest.TestCase):
    def test_korean_format(self):
        self.assertEqual(sh.release_date_iso("2026년 09월 21일"), "2026-09-21")

    def test_unparsable(self):
        self.assertIsNone(sh.release_date_iso("출간일 정보 없음"))
        self.assertIsNone(sh.release_date_iso(None))


class MergeCatalogTest(unittest.TestCase):
    def test_new_book_gets_first_and_last_seen(self):
        catalog = sh.merge_catalog({}, {"영진닷컴": [book("1", "A")]}, "2026-09-24")
        entry = catalog["1"]
        self.assertEqual(entry["publisher"], "영진닷컴")
        self.assertEqual(entry["first_seen"], "2026-09-24")
        self.assertEqual(entry["last_seen"], "2026-09-24")
        self.assertEqual(entry["title"], "A")

    def test_existing_book_keeps_first_seen_and_refreshes(self):
        catalog = sh.merge_catalog({}, {"영진닷컴": [book("1", "A")]}, "2026-09-20")
        sh.merge_catalog(catalog, {"영진닷컴": [book("1", "A 개정판")]}, "2026-09-24")
        entry = catalog["1"]
        self.assertEqual(entry["first_seen"], "2026-09-20")
        self.assertEqual(entry["last_seen"], "2026-09-24")
        self.assertEqual(entry["title"], "A 개정판")

    def test_same_goods_no_under_two_publishers_is_one_entry(self):
        lists = {"길벗": [book("1")], "길벗캠퍼스": [book("1")]}
        catalog = sh.merge_catalog({}, lists, "2026-09-24")
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog["1"]["publisher"], "길벗")

    def test_empty_goods_no_skipped(self):
        catalog = sh.merge_catalog({}, {"길벗": [book("")]}, "2026-09-24")
        self.assertEqual(catalog, {})

    def test_absent_book_keeps_last_seen(self):
        catalog = sh.merge_catalog({}, {"길벗": [book("1")]}, "2026-09-20")
        sh.merge_catalog(catalog, {"길벗": [book("2")]}, "2026-09-24")
        self.assertEqual(catalog["1"]["last_seen"], "2026-09-20")
        self.assertEqual(catalog["2"]["first_seen"], "2026-09-24")

    def test_list_release_date_used_when_catalog_has_none(self):
        catalog = sh.merge_catalog({}, {"길벗": [book("1", release_date="2026년 10월 01일")]}, "2026-09-24")
        self.assertEqual(catalog["1"]["release_date"], "2026년 10월 01일")

    def test_apply_release_dates_from_details(self):
        catalog = sh.merge_catalog({}, {"길벗": [book("1")]}, "2026-09-24")
        sh.apply_release_dates(catalog, {"1": ("2026년 09월 01일", "10"), "9": ("2026년 01월 01일", "1")})
        self.assertEqual(catalog["1"]["release_date"], "2026년 09월 01일")
        sh.apply_release_dates(catalog, {"1": None})
        self.assertEqual(catalog["1"]["release_date"], "2026년 09월 01일")


class CatalogFileTest(unittest.TestCase):
    def test_round_trip_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "books.json"
            self.assertEqual(sh.load_catalog(path), {})
            catalog = sh.merge_catalog({}, {"길벗": [book("1", "한글 제목")]}, "2026-09-24")
            sh.save_catalog(path, catalog)
            self.assertEqual(sh.load_catalog(path), catalog)
            self.assertIn("한글 제목", path.read_text(encoding="utf-8"))


class HistoryTest(unittest.TestCase):
    def test_upsert_writes_sorted_rows_with_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            hdir = Path(tmp) / "history"
            self.assertEqual(sh.load_history(hdir), {})
            written = sh.upsert_day(hdir, "2026-09-24", {"20": 5, "10": 3})
            self.assertEqual(written, 2)
            lines = (hdir / "2026-09.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines, ["date,goods_no,sell_num", "2026-09-24,10,3", "2026-09-24,20,5"])

    def test_same_day_rerun_replaces_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            hdir = Path(tmp) / "history"
            sh.upsert_day(hdir, "2026-09-24", {"10": 3, "20": 5})
            sh.upsert_day(hdir, "2026-09-24", {"10": 4})
            history = sh.load_history(hdir)
            self.assertEqual(history, {"10": [("2026-09-24", 4)]})

    def test_shards_merge_in_date_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            hdir = Path(tmp) / "history"
            sh.upsert_day(hdir, "2026-10-01", {"10": 9})
            sh.upsert_day(hdir, "2026-09-30", {"10": 7})
            sh.upsert_day(hdir, "2026-09-24", {"10": 3, "20": 1})
            self.assertEqual(sorted(p.name for p in hdir.glob("*.csv")), ["2026-09.csv", "2026-10.csv"])
            history = sh.load_history(hdir)
            self.assertEqual(history["10"], [("2026-09-24", 3), ("2026-09-30", 7), ("2026-10-01", 9)])
            self.assertEqual(history["20"], [("2026-09-24", 1)])


class DeltaTest(unittest.TestCase):
    def test_exact_baseline(self):
        points = [("2026-09-17", 100), ("2026-09-20", 120), ("2026-09-24", 150)]
        self.assertEqual(sh.compute_delta(points, 7), (50, 7))

    def test_nearest_earlier_baseline(self):
        points = [("2026-09-16", 100), ("2026-09-20", 120), ("2026-09-24", 150)]
        self.assertEqual(sh.compute_delta(points, 7), (50, 8))

    def test_partial_history(self):
        points = [("2026-09-21", 100), ("2026-09-24", 130)]
        self.assertEqual(sh.compute_delta(points, 7), (30, 3))

    def test_single_point(self):
        self.assertEqual(sh.compute_delta([("2026-09-24", 100)], 7), (None, None))
        self.assertEqual(sh.compute_delta([], 7), (None, None))


class BuildSalesDataTest(unittest.TestCase):
    def setUp(self):
        self.today = "2026-09-24"
        self.catalog = {
            "1": {"title": "신간", "author": "a", "publisher": "영진닷컴", "image_url": "", "detail_url": "",
                  "release_date": "2026년 09월 20일", "first_seen": "2026-09-21", "last_seen": self.today},
            "2": {"title": "구간", "author": "b", "publisher": "영진닷컴", "image_url": "", "detail_url": "",
                  "release_date": "2025년 01월 01일", "first_seen": "2026-06-01", "last_seen": self.today},
            "3": {"title": "예약", "author": "c", "publisher": "길벗", "image_url": "", "detail_url": "",
                  "release_date": "출간일 정보 없음", "first_seen": self.today, "last_seen": self.today},
        }
        self.history = {
            "1": [("2026-09-21", 10), ("2026-09-22", 20), ("2026-09-24", 40)],
            "2": [("2026-06-01", 500), ("2026-09-17", 900), ("2026-09-24", 1000)],
        }
        self.data = sh.build_sales_data(self.catalog, self.history, self.today, ["길벗", "영진닷컴"])
        self.books = {b["goods_no"]: b for b in self.data["books"]}

    def test_dates_are_trimmed_to_window(self):
        self.assertEqual(self.data["dates"], ["2026-09-17", "2026-09-21", "2026-09-22", "2026-09-24"])
        self.assertEqual(self.data["latest_date"], "2026-09-24")

    def test_series_alignment_with_gap(self):
        b = self.books["1"]
        self.assertEqual(b["series_start"], 1)
        self.assertEqual(b["series"], [10, 20, 40])
        self.assertEqual(b["latest"], 40)
        self.assertEqual(b["latest_date"], "2026-09-24")

    def test_delta1_uses_previous_point(self):
        self.assertEqual((self.books["1"]["delta1"], self.books["1"]["delta1_days"]), (20, 2))  # 09-22 -> 09-24
        self.assertEqual((self.books["2"]["delta1"], self.books["2"]["delta1_days"]), (100, 7))
        self.assertIsNone(self.books["3"]["delta1"])

    def test_delta3(self):
        self.assertEqual((self.books["1"]["delta3"], self.books["1"]["delta3_days"]), (30, 3))  # 09-21 -> 09-24
        self.assertEqual((self.books["2"]["delta3"], self.books["2"]["delta3_days"]), (100, 7))

    def test_series_ignores_points_before_window_but_deltas_use_them(self):
        b = self.books["2"]
        self.assertEqual(b["series_start"], 0)
        self.assertEqual(b["series"], [900, None, None, 1000])
        self.assertEqual((b["delta7"], b["delta7_days"]), (100, 7))
        self.assertEqual((b["delta30"], b["delta30_days"]), (500, 115))

    def test_book_without_history(self):
        b = self.books["3"]
        self.assertIsNone(b["latest"])
        self.assertNotIn("series", b)
        self.assertIsNone(b["release_date"])
        self.assertIsNone(b["delta7"])

    def test_release_date_iso(self):
        self.assertEqual(self.books["1"]["release_date"], "2026-09-20")

    def test_publisher_order_and_stats(self):
        pubs = self.data["publishers"]
        self.assertEqual([p["name"] for p in pubs], ["길벗", "영진닷컴"])
        gilbut, youngjin = pubs
        self.assertEqual(gilbut["book_count"], 0)
        self.assertIsNone(gilbut["new_avg"])
        self.assertEqual(youngjin["book_count"], 2)
        self.assertEqual(youngjin["total"], 1040)
        self.assertEqual(youngjin["avg"], 520)
        self.assertEqual(youngjin["delta7"], 130)
        self.assertEqual(youngjin["new_count"], 1)
        self.assertEqual(youngjin["new_avg"], 40)
        self.assertEqual(youngjin["new_delta7"], 30)
        self.assertEqual(youngjin["top_goods_no"], "2")

    def test_window_size_parameter(self):
        data = sh.build_sales_data(self.catalog, self.history, self.today, [], series_days=3)
        self.assertEqual(data["dates"], ["2026-09-22", "2026-09-24"])


if __name__ == "__main__":
    unittest.main()
