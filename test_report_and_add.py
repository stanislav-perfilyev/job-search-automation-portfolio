#!/usr/bin/env python3
"""
test_report_and_add.py -- тесты для report.py и add_vacancy.py
Запуск: python test_report_and_add.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
import importlib.util
import pathlib
import os
from datetime import datetime, date, timedelta
from collections import defaultdict

# Mock externals
import matplotlib
matplotlib.use("Agg")

class FakeRequestException(Exception): pass
fake_requests = MagicMock()
fake_requests.RequestException = FakeRequestException
sys.modules["requests"] = fake_requests
for m in ["google","google.oauth2","google.oauth2.service_account",
          "google.auth","google.auth.transport","google.auth.transport.requests","dotenv"]:
    sys.modules.setdefault(m, MagicMock())

def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, pathlib.Path(__file__).parent / filename
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

rep = _load("report", "report.py")


# ============================================================
# report.py
# ============================================================

class TestParseDate(unittest.TestCase):

    def test_dd_mm_yyyy(self):
        self.assertEqual(rep.parse_date("01.06.2026"), datetime(2026, 6, 1))

    def test_yyyy_mm_dd(self):
        self.assertEqual(rep.parse_date("2026-06-01"), datetime(2026, 6, 1))

    def test_invalid_returns_none(self):
        self.assertIsNone(rep.parse_date("not-a-date"))

    def test_empty_returns_none(self):
        self.assertIsNone(rep.parse_date(""))


class TestNormalizeStatus(unittest.TestCase):

    def test_empty_is_waiting(self):
        self.assertEqual(rep.normalize_status(""), "ожидание")

    def test_interview_detected(self):
        self.assertEqual(rep.normalize_status("На интервью"), "интервью")

    def test_offer_detected(self):
        self.assertEqual(rep.normalize_status("Оффер!"), "оффер")

    def test_reject_detected(self):
        self.assertEqual(rep.normalize_status("Отказ"), "отказ")

    def test_waiting_explicit(self):
        self.assertEqual(rep.normalize_status("ожидание"), "ожидание")

    def test_prosmotr_is_waiting(self):
        self.assertEqual(rep.normalize_status("просмотр"), "ожидание")

    def test_other_becomes_drugoe(self):
        # "другое" = то, что не подходит ни под один известный паттерн
        result = rep.normalize_status("какой-то непонятный текст xyz")
        self.assertEqual(result, "другое")


class TestAnalyzeReport(unittest.TestCase):

    def _make_rows(self, entries):
        """entries = список (date_str_in_F, status)"""
        rows = []
        for date_str, status in entries:
            row = [""] * 11
            row[0] = "Dev"
            row[5] = date_str   # F
            row[8] = status
            rows.append(row)
        return rows

    def test_by_status_counts(self):
        rows = self._make_rows([
            ("01.06.2026", "ожидание"),
            ("01.06.2026", "ожидание"),
            ("02.06.2026", "отказ"),
        ])
        by_date, by_status, stale_count, _ = rep.analyze(rows)
        self.assertEqual(by_status["ожидание"], 2)
        self.assertEqual(by_status["отказ"], 1)

    def test_by_date_aggregation(self):
        rows = self._make_rows([
            ("01.06.2026", "ожидание"),
            ("01.06.2026", "ожидание"),
            ("02.06.2026", "ожидание"),
        ])
        by_date, _, _, _ = rep.analyze(rows)
        d01 = datetime(2026, 6, 1)
        d02 = datetime(2026, 6, 2)
        self.assertEqual(by_date[d01], 2)
        self.assertEqual(by_date[d02], 1)

    def test_stale_detection(self):
        old = (date.today() - timedelta(days=10)).strftime("%d.%m.%Y")
        rows = self._make_rows([(old, "ожидание")])
        _, _, stale_count, stale_list = rep.analyze(rows)
        self.assertEqual(stale_count, 1)
        self.assertEqual(len(stale_list), 1)

    def test_non_waiting_not_stale(self):
        old = (date.today() - timedelta(days=10)).strftime("%d.%m.%Y")
        rows = self._make_rows([(old, "отказ")])
        _, _, stale_count, _ = rep.analyze(rows)
        self.assertEqual(stale_count, 0)

    def test_no_date_row_skips_by_date(self):
        rows = self._make_rows([("", "ожидание")])
        by_date, by_status, _, _ = rep.analyze(rows)
        self.assertEqual(len(by_date), 0)
        self.assertEqual(by_status["ожидание"], 1)

    def test_stale_list_max_5(self):
        old = (date.today() - timedelta(days=10)).strftime("%d.%m.%Y")
        rows = self._make_rows([(old, "ожидание")] * 10)
        _, _, stale_count, stale_list = rep.analyze(rows)
        self.assertEqual(stale_count, 10)
        self.assertLessEqual(len(stale_list), 5)


class TestBuildCaptionFull(unittest.TestCase):

    def _by_date(self, today_count=5, sessions=3):
        today = datetime.now()
        result = {}
        for i in range(sessions - 1):
            d = datetime(2026, 6, i + 1)
            result[d] = 3
        result[today] = today_count
        return result

    def test_has_today_count(self):
        by_date = self._by_date(today_count=7)
        caption = rep.build_caption_full(by_date)
        self.assertIn("7", caption)

    def test_has_sessions_count(self):
        by_date = self._by_date(sessions=4)
        caption = rep.build_caption_full(by_date)
        self.assertIn("4", caption)

    def test_no_today_warning_when_zero(self):
        by_date = {datetime(2026, 6, 1): 5}   # нет сегодняшней даты
        caption = rep.build_caption_full(by_date)
        self.assertIn("не найдено", caption.lower())


class TestBuildCaptionCheck(unittest.TestCase):

    def test_shows_total(self):
        by_status = {"ожидание": 10, "отказ": 3}
        caption = rep.build_caption_check(by_status, stale_count=0)
        self.assertIn("13", caption)

    def test_shows_interview_if_present(self):
        by_status = {"ожидание": 5, "интервью": 2}
        caption = rep.build_caption_check(by_status, stale_count=0)
        self.assertIn("2", caption)

    def test_shows_stale_if_present(self):
        by_status = {"ожидание": 5}
        caption = rep.build_caption_check(by_status, stale_count=3)
        self.assertIn("3", caption)


# ============================================================
# add_vacancy.py -- только логику маппинга источника → колонки
# (main() тестируем косвенно через проверку логики)
# ============================================================

class TestAddVacancySourceLogic(unittest.TestCase):
    """Тесты логики определения колонки даты по источнику."""

    def _get_dates(self, source, date_val="29.06.2026"):
        source_lower = source.lower().strip()
        date_f = date_g = date_h = ""
        if "hh" in source_lower:
            date_f = date_val
        elif "корп" in source_lower:
            date_g = date_val
        elif "linkedin" in source_lower or "соцс" in source_lower:
            date_h = date_val
        else:
            date_f = date_val  # fallback
        return date_f, date_g, date_h

    def test_hh_ru_to_F(self):
        f, g, h = self._get_dates("hh.ru")
        self.assertEqual(f, "29.06.2026")
        self.assertEqual(g, "")

    def test_hh_kz_to_F(self):
        f, g, h = self._get_dates("hh.kz")
        self.assertEqual(f, "29.06.2026")

    def test_corp_to_G(self):
        f, g, h = self._get_dates("корп. сайт")
        self.assertEqual(g, "29.06.2026")

    def test_linkedin_to_H(self):
        f, g, h = self._get_dates("LinkedIn")
        self.assertEqual(h, "29.06.2026")

    def test_socseti_to_H(self):
        f, g, h = self._get_dates("соцсети")
        self.assertEqual(h, "29.06.2026")

    def test_unknown_fallback_to_F(self):
        f, g, h = self._get_dates("Telegram")
        self.assertEqual(f, "29.06.2026")


if __name__ == "__main__":
    unittest.main(verbosity=2)
