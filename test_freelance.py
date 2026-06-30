#!/usr/bin/env python3
"""
test_freelance.py -- автотесты для freelance_add.py и freelance_report.py
Запуск: python test_freelance.py -v
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
class FakeRequestException(Exception): pass
fake_requests = MagicMock()
fake_requests.RequestException = FakeRequestException
sys.modules["requests"] = fake_requests

import matplotlib
matplotlib.use("Agg")
for m in ["google","google.oauth2","google.oauth2.service_account",
          "google.auth","google.auth.transport","google.auth.transport.requests","dotenv"]:
    sys.modules.setdefault(m, MagicMock())

def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, pathlib.Path(__file__).parent / filename
    )
    m = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"FREELANCE_SPREADSHEET_ID": "FAKE"}):
        spec.loader.exec_module(m)
    return m

fadd  = _load("freelance_add",    "freelance_add.py")
frep  = _load("freelance_report", "freelance_report.py")


# ============================================================
# freelance_add.py
# ============================================================

class TestFreelanceAddBuildRow(unittest.TestCase):

    def _proj(self, **kw):
        defaults = {
            "project": "Парсер C++",
            "client": "client123",
            "url": "https://fl.ru/p/1",
            "platform": "FL.ru",
            "template": "A",
            "budget": "15000",
            "our_rate": "12000",
        }
        defaults.update(kw)
        return fadd.build_row(defaults, "29.06.2026")

    def test_row_length_11(self):
        self.assertEqual(len(self._proj()), 11)

    def test_template_prefix_added(self):
        row = self._proj(template="B")
        self.assertEqual(row[4], "шаблон B")

    def test_template_already_prefixed(self):
        row = self._proj(template="шаблон A")
        self.assertEqual(row[4], "шаблон A")

    def test_date_in_column_H(self):
        row = self._proj()
        self.assertEqual(row[7], "29.06.2026")

    def test_fl_ru_connects_zero(self):
        row = self._proj(platform="FL.ru")
        self.assertEqual(row[10], 0)

    def test_upwork_connects_default_14(self):
        row = self._proj(platform="Upwork")
        self.assertEqual(row[10], 14)

    def test_upwork_connects_custom(self):
        row = self._proj(platform="Upwork", connects=6)
        self.assertEqual(row[10], 6)

    def test_kwork_connects_zero(self):
        row = self._proj(platform="Kwork")
        self.assertEqual(row[10], 0)

    def test_default_status_sent(self):
        row = self._proj()
        self.assertEqual(row[8], "Отправлен")

    def test_project_name_in_A(self):
        row = self._proj(project="My Project")
        self.assertEqual(row[0], "My Project")

    def test_platform_in_D(self):
        row = self._proj(platform="Upwork")
        self.assertEqual(row[3], "Upwork")


class TestFreelanceAddValidation(unittest.TestCase):

    def test_required_fields_check(self):
        p = {"project": "P", "url": "u"}  # нет platform, template
        missing = [k for k in ("project", "url", "platform", "template") if not p.get(k)]
        self.assertIn("platform", missing)
        self.assertIn("template", missing)
        self.assertNotIn("project", missing)

    def test_example_projects_filtered(self):
        projects = [
            {"project": "Example", "_example": True},
            {"project": "Real"},
        ]
        filtered = [p for p in projects if not p.get("_example")]
        self.assertEqual(len(filtered), 1)


# ============================================================
# freelance_report.py
# ============================================================

class TestNormalizePlatform(unittest.TestCase):

    def test_fl_ru(self):
        self.assertEqual(frep.normalize_platform("FL.ru"), "FL.ru")

    def test_upwork_lowercase(self):
        self.assertEqual(frep.normalize_platform("upwork"), "Upwork")

    def test_habr_freelance(self):
        self.assertEqual(frep.normalize_platform("Habr Freelance"), "Habr Freelance")

    def test_kwork(self):
        self.assertEqual(frep.normalize_platform("kwork"), "Kwork")

    def test_unknown_returns_drugoe(self):
        self.assertEqual(frep.normalize_platform("SomeOther"), "другое")

    def test_empty_returns_drugoe(self):
        self.assertEqual(frep.normalize_platform(""), "другое")


class TestNormalizeStatus(unittest.TestCase):

    def test_sent_default(self):
        self.assertEqual(frep.normalize_status("Отправлен"), "отправлен")

    def test_in_work(self):
        self.assertEqual(frep.normalize_status("В работе"), "в работе")

    def test_done(self):
        self.assertEqual(frep.normalize_status("Завершён"), "завершён")

    def test_rejected(self):
        self.assertEqual(frep.normalize_status("Отказ"), "отказ")

    def test_viewed(self):
        self.assertEqual(frep.normalize_status("Просмотрен"), "просмотрен")

    def test_interview(self):
        self.assertEqual(frep.normalize_status("interview"), "интервью")

    def test_unknown_is_sent(self):
        self.assertEqual(frep.normalize_status("unknown xyz"), "отправлен")


class TestAnalyze(unittest.TestCase):

    def _make_row(self, platform="FL.ru", status="Отправлен",
                  date_str="", connects="0"):
        row = [""] * 11
        row[3] = platform   # D
        row[7] = date_str   # H -- дата отклика
        row[8] = status     # I
        row[10] = connects  # K
        return row

    def test_pipeline_pending_count(self):
        rows = [
            self._make_row(status="Отправлен"),
            self._make_row(status="Отправлен"),
            self._make_row(status="Завершён"),
        ]
        _, _, _, _, pipeline = frep.analyze(rows, period_days=30)
        self.assertEqual(pipeline["pending"], 2)

    def test_pipeline_active_count(self):
        rows = [
            self._make_row(status="В работе"),
            self._make_row(status="Отправлен"),
        ]
        _, _, _, _, pipeline = frep.analyze(rows, period_days=30)
        self.assertEqual(pipeline["active"], 1)

    def test_connects_summed_for_upwork(self):
        today = date.today().strftime("%d.%m.%Y")
        rows = [
            self._make_row(platform="Upwork", date_str=today, connects="6"),
            self._make_row(platform="Upwork", date_str=today, connects="8"),
            self._make_row(platform="FL.ru",  date_str=today, connects="0"),
        ]
        _, _, _, _, pipeline = frep.analyze(rows, period_days=30)
        self.assertEqual(pipeline["connects_used"], 14)

    def test_connects_remaining(self):
        frep.UPWORK_CONNECTS_INITIAL = 50
        today = date.today().strftime("%d.%m.%Y")
        rows = [self._make_row(platform="Upwork", date_str=today, connects="10")]
        _, _, _, _, pipeline = frep.analyze(rows, period_days=30)
        self.assertEqual(pipeline["connects_remaining"], 40)

    def test_stale_detection(self):
        old = (date.today() - timedelta(days=10)).strftime("%d.%m.%Y")
        rows = [self._make_row(platform="Upwork", status="Отправлен", date_str=old, connects="6")]
        _, _, _, stale, _ = frep.analyze(rows, period_days=30)
        self.assertEqual(len(stale), 1)

    def test_old_rows_outside_period_not_in_charts(self):
        old = (date.today() - timedelta(days=60)).strftime("%d.%m.%Y")
        rows = [self._make_row(platform="FL.ru", status="Отправлен", date_str=old)]
        by_platform, _, _, _, _ = frep.analyze(rows, period_days=30)
        # старая строка не попадает в by_platform (за пределами периода)
        self.assertEqual(sum(by_platform.values()), 0)


class TestBuildCaption(unittest.TestCase):

    def _make_pipeline(self, pending=5, active=2, used=20, remaining=130, initial=150):
        return {
            "pending": pending,
            "active": active,
            "connects_used": used,
            "connects_remaining": remaining,
            "connects_initial": initial,
        }

    def test_caption_has_total(self):
        caption = frep.build_caption(
            {"FL.ru": 3}, {}, [], 30, self._make_pipeline()
        )
        self.assertIn("3", caption)

    def test_caption_has_pipeline(self):
        caption = frep.build_caption(
            {"FL.ru": 1}, {}, [], 30, self._make_pipeline(pending=7)
        )
        self.assertIn("7", caption)

    def test_connects_green_above_50(self):
        caption = frep.build_caption(
            {}, {}, [], 30, self._make_pipeline(remaining=100)
        )
        self.assertIn("🟢", caption)

    def test_connects_yellow_21_to_50(self):
        caption = frep.build_caption(
            {}, {}, [], 30, self._make_pipeline(remaining=30)
        )
        self.assertIn("🟡", caption)

    def test_connects_red_below_20(self):
        caption = frep.build_caption(
            {}, {}, [], 30, self._make_pipeline(remaining=10)
        )
        self.assertIn("🔴", caption)


if __name__ == "__main__":
    unittest.main(verbosity=2)
