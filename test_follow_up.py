#!/usr/bin/env python3
"""
test_follow_up.py -- автотесты для follow_up.py
Запуск: python test_follow_up.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
import importlib.util
import pathlib
import os
from datetime import datetime, date, timedelta

# Mock externals
class FakeRequestException(Exception):
    pass
fake_requests = MagicMock()
fake_requests.RequestException = FakeRequestException
sys.modules["requests"] = fake_requests
for m in ["google","google.oauth2","google.oauth2.service_account",
          "google.auth","google.auth.transport","google.auth.transport.requests","dotenv"]:
    sys.modules.setdefault(m, MagicMock())

spec = importlib.util.spec_from_file_location(
    "follow_up",
    pathlib.Path(__file__).parent / "follow_up.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestParseDate(unittest.TestCase):

    def test_dd_mm_yyyy(self):
        d = mod.parse_date("29.06.2026")
        self.assertEqual(d, datetime(2026, 6, 29))

    def test_yyyy_mm_dd(self):
        d = mod.parse_date("2026-06-29")
        self.assertEqual(d, datetime(2026, 6, 29))

    def test_dd_slash_mm_slash_yyyy(self):
        d = mod.parse_date("29/06/2026")
        self.assertEqual(d, datetime(2026, 6, 29))

    def test_invalid_returns_none(self):
        self.assertIsNone(mod.parse_date("not-a-date"))

    def test_empty_returns_none(self):
        self.assertIsNone(mod.parse_date(""))

    def test_strips_whitespace(self):
        d = mod.parse_date("  29.06.2026  ")
        self.assertEqual(d, datetime(2026, 6, 29))


class TestNormalizeStatus(unittest.TestCase):

    def test_waiting_is_waiting(self):
        self.assertEqual(mod.normalize_status("ожидание"), "ожидание")

    def test_empty_is_waiting(self):
        self.assertEqual(mod.normalize_status(""), "ожидание")

    def test_interview_detected(self):
        self.assertEqual(mod.normalize_status("Интервью запланировано"), "интервью")

    def test_sobeses_detected(self):
        self.assertEqual(mod.normalize_status("Приглашение на собес"), "интервью")

    def test_offer_detected(self):
        self.assertEqual(mod.normalize_status("Оффер получен"), "оффер")

    def test_reject_detected(self):
        self.assertEqual(mod.normalize_status("Отказ"), "отказ")

    def test_case_insensitive(self):
        self.assertEqual(mod.normalize_status("ОТКАЗ"), "отказ")


class TestFindStale(unittest.TestCase):
    """Тесты find_stale() -- поиск зависших откликов"""

    def _make_row(self, vacancy="Dev", company="Co", url="u",
                  source="hh.kz", status="ожидание", date_str=""):
        """11 колонок как в реальной таблице."""
        row = [""] * 11
        row[0] = vacancy
        row[1] = company
        row[2] = url
        row[3] = source
        row[8] = status
        row[5] = date_str   # F -- hh date
        return row

    def test_old_waiting_is_stale(self):
        old_date = (date.today() - timedelta(days=10)).strftime("%d.%m.%Y")
        rows = [self._make_row(status="ожидание", date_str=old_date)]
        stale = mod.find_stale(rows, days=7)
        self.assertEqual(len(stale), 1)

    def test_recent_waiting_is_not_stale(self):
        new_date = (date.today() - timedelta(days=3)).strftime("%d.%m.%Y")
        rows = [self._make_row(status="ожидание", date_str=new_date)]
        stale = mod.find_stale(rows, days=7)
        self.assertEqual(len(stale), 0)

    def test_non_waiting_status_skipped(self):
        old_date = (date.today() - timedelta(days=10)).strftime("%d.%m.%Y")
        rows = [self._make_row(status="интервью", date_str=old_date)]
        stale = mod.find_stale(rows, days=7)
        self.assertEqual(len(stale), 0)

    def test_no_date_skipped(self):
        rows = [self._make_row(status="ожидание", date_str="")]
        stale = mod.find_stale(rows, days=7)
        self.assertEqual(len(stale), 0)

    def test_sorted_by_age_descending(self):
        date_15 = (date.today() - timedelta(days=15)).strftime("%d.%m.%Y")
        date_10 = (date.today() - timedelta(days=10)).strftime("%d.%m.%Y")
        rows = [
            self._make_row(vacancy="Younger", date_str=date_10),
            self._make_row(vacancy="Older", date_str=date_15),
        ]
        stale = mod.find_stale(rows, days=7)
        self.assertEqual(stale[0]["vacancy"], "Older")
        self.assertEqual(stale[1]["vacancy"], "Younger")

    def test_age_calculated_correctly(self):
        target_date = date.today() - timedelta(days=12)
        rows = [self._make_row(
            status="ожидание",
            date_str=target_date.strftime("%d.%m.%Y"),
        )]
        stale = mod.find_stale(rows, days=7)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["age"], 12)

    def test_rejection_status_skipped(self):
        old_date = (date.today() - timedelta(days=10)).strftime("%d.%m.%Y")
        rows = [self._make_row(status="отказ", date_str=old_date)]
        stale = mod.find_stale(rows, days=7)
        self.assertEqual(len(stale), 0)


class TestFormatOutput(unittest.TestCase):
    """Тесты форматирования"""

    def _item(self, age=10):
        return {
            "row": 5,
            "vacancy": "C++ Developer",
            "company": "Яндекс",
            "source": "hh.kz",
            "url": "https://hh.kz/vacancy/1",
            "age": age,
            "date": "19.06.2026",
        }

    def test_console_format_has_vacancy_name(self):
        text = mod.format_console([self._item()], days=7)
        self.assertIn("C++ Developer", text)

    def test_console_format_has_company(self):
        text = mod.format_console([self._item()], days=7)
        self.assertIn("Яндекс", text)

    def test_console_format_shows_count(self):
        text = mod.format_console([self._item()] * 3, days=7)
        self.assertIn("3", text)

    def test_telegram_format_html_tags(self):
        text = mod.format_telegram([self._item()], days=7)
        self.assertIn("<b>", text)

    def test_telegram_format_red_icon_for_old(self):
        text = mod.format_telegram([self._item(age=20)], days=7)
        self.assertIn("🔴", text)

    def test_telegram_format_orange_icon_for_medium(self):
        text = mod.format_telegram([self._item(age=10)], days=7)
        self.assertIn("🟠", text)

    def test_telegram_format_yellow_icon_for_recent(self):
        text = mod.format_telegram([self._item(age=7)], days=7)
        self.assertIn("🟡", text)

    def test_telegram_limits_to_15(self):
        items = [self._item() for _ in range(20)]
        text = mod.format_telegram(items, days=7)
        self.assertIn("ещё 5", text)

    def test_empty_stale_list(self):
        text = mod.format_console([], days=7)
        self.assertIn("0", text)


class TestFollowUpTemplate(unittest.TestCase):

    def test_template_has_vacancy_placeholder(self):
        self.assertIn("{vacancy}", mod.FOLLOW_UP_TEMPLATE)

    def test_template_has_company_placeholder(self):
        self.assertIn("{company}", mod.FOLLOW_UP_TEMPLATE)

    def test_template_formats_correctly(self):
        result = mod.FOLLOW_UP_TEMPLATE.format(vacancy="C++ Dev", company="Яндекс")
        self.assertIn("C++ Dev", result)
        self.assertIn("Яндекс", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
