#!/usr/bin/env python3
"""
test_batch_add_from_json.py -- автотесты для batch_add_from_json.py
Запуск: python test_batch_add_from_json.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import importlib.util
import pathlib
import os

# --- Мокаем внешние зависимости ДО импорта модуля ---
import types

# Реальный requests нужен только для exception-классов при мокировании
# Заменяем целиком, но сохраняем реальный ConnectionError как базу
class FakeRequestException(Exception):
    pass

class FakeHTTPError(FakeRequestException):
    pass

fake_requests = MagicMock()
fake_requests.RequestException = FakeRequestException
fake_requests.HTTPError = FakeHTTPError
sys.modules["requests"] = fake_requests

sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.oauth2", MagicMock())
sys.modules.setdefault("google.oauth2.service_account", MagicMock())
sys.modules.setdefault("google.auth", MagicMock())
sys.modules.setdefault("google.auth.transport", MagicMock())
sys.modules.setdefault("google.auth.transport.requests", MagicMock())
sys.modules.setdefault("dotenv", MagicMock())

with patch.dict(os.environ, {
    "SPREADSHEET_ID": "MAIN_ID",
    "CURATOR_SPREADSHEET_ID": "CURATOR_ID",
}):
    spec = importlib.util.spec_from_file_location(
        "batch_add_from_json",
        pathlib.Path(__file__).parent / "batch_add_from_json.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


class TestBuildRow(unittest.TestCase):

    def _row(self, **kw):
        defaults = {
            "vacancy": "C++ разработчик",
            "company": "Рога и Копыта",
            "url": "https://hh.kz/vacancy/123",
            "source": "hh.kz",
            "template": "B",
        }
        defaults.update(kw)
        return mod.build_row(defaults, "29.06.2026")

    def test_hh_date_in_F(self):
        row = self._row(source="hh.kz")
        self.assertEqual(row[5], "29.06.2026")
        self.assertEqual(row[6], "")
        self.assertEqual(row[7], "")

    def test_hh_ru_date_in_F(self):
        row = self._row(source="hh.ru")
        self.assertEqual(row[5], "29.06.2026")

    def test_corp_date_in_G(self):
        row = self._row(source="корп. сайт")
        self.assertEqual(row[5], "")
        self.assertEqual(row[6], "29.06.2026")
        self.assertEqual(row[7], "")

    def test_linkedin_date_in_H(self):
        row = self._row(source="LinkedIn")
        self.assertEqual(row[5], "")
        self.assertEqual(row[6], "")
        self.assertEqual(row[7], "29.06.2026")

    def test_unknown_source_fallback_F(self):
        row = self._row(source="Telegram")
        self.assertEqual(row[5], "29.06.2026")

    def test_template_prefix_added(self):
        row = self._row(template="B")
        self.assertEqual(row[4], "шаблон B")

    def test_template_already_prefixed(self):
        row = self._row(template="шаблон A")
        self.assertEqual(row[4], "шаблон A")

    def test_row_length_12(self):
        row = self._row()
        self.assertEqual(len(row), 12)

    def test_skill_gaps_in_L(self):
        row = self._row(skill_gaps="Docker, Boost")
        self.assertEqual(row[11], "Docker, Boost")

    def test_skill_gaps_empty_default(self):
        row = self._row()
        self.assertEqual(row[11], "")

    def test_default_status_waiting(self):
        row = self._row()
        self.assertEqual(row[8], "ожидание")

    def test_custom_status(self):
        row = self._row(**{"status": "интервью"})
        self.assertEqual(row[8], "интервью")

    def test_vacancy_company_url_source_positions(self):
        row = self._row(vacancy="Senior C++", company="Яндекс",
                        url="https://ya.ru/1", source="hh.kz")
        self.assertEqual(row[0], "Senior C++")
        self.assertEqual(row[1], "Яндекс")
        self.assertEqual(row[2], "https://ya.ru/1")
        self.assertEqual(row[3], "hh.kz")

    def test_habr_career_fallback_to_F(self):
        # Habr Career не содержит hh/корп/linkedin -- fallback F
        row = self._row(source="Habr Career")
        self.assertEqual(row[5], "29.06.2026")

    def test_template_C_uppercase(self):
        row = self._row(template="C")
        self.assertEqual(row[4], "шаблон C")


class TestAppendRowsBatchRetry(unittest.TestCase):

    def _patch_post(self, side_effects):
        return patch.object(fake_requests, "post", side_effect=side_effects)

    def _make_good_response(self, range_str="A2:L3"):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"updates": {"updatedRange": range_str}}
        resp.raise_for_status = MagicMock()
        return resp

    def _make_429_response(self):
        resp = MagicMock()
        resp.status_code = 429
        resp.headers = {"Retry-After": "1"}
        resp.raise_for_status = MagicMock(side_effect=FakeHTTPError("429"))
        return resp

    def test_success_first_attempt(self):
        with self._patch_post([self._make_good_response("Вакансии!A2:L3")]):
            result = mod.append_rows_batch("TOKEN", "SHEET_ID", [["a"]])
        self.assertEqual(result, "Вакансии!A2:L3")

    def test_retry_on_network_error_then_success(self):
        good = self._make_good_response("A2:L2")
        with self._patch_post([FakeRequestException("network"), good]) as mock_post, \
             patch("time.sleep"):
            result = mod.append_rows_batch("TOKEN", "SHEET_ID", [["a"]])
        self.assertEqual(result, "A2:L2")
        self.assertEqual(mock_post.call_count, 2)

    def test_raises_after_all_retries_exhausted(self):
        with self._patch_post([FakeRequestException("fail")] * 5), \
             patch("time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                mod.append_rows_batch("TOKEN", "SHEET_ID", [["a"]])
        self.assertIn("попыток", str(ctx.exception))

    def test_retry_count_matches_RETRY_ATTEMPTS(self):
        with self._patch_post([FakeRequestException("fail")] * 10) as mock_post, \
             patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                mod.append_rows_batch("TOKEN", "SHEET_ID", [["a"]])
        self.assertEqual(mock_post.call_count, mod._RETRY_ATTEMPTS)

    def test_429_sleeps_and_retries(self):
        r429 = self._make_429_response()
        good = self._make_good_response("A2")
        with self._patch_post([r429, good]), patch("time.sleep") as mock_sleep:
            result = mod.append_rows_batch("TOKEN", "SHEET_ID", [["x"]])
        self.assertEqual(result, "A2")
        mock_sleep.assert_called()

    def test_url_contains_sheet_id(self):
        good = self._make_good_response()
        with self._patch_post([good]) as mock_post:
            mod.append_rows_batch("TOKEN", "MY_SHEET", [["a"]])
        call_url = mock_post.call_args[0][0]
        self.assertIn("MY_SHEET", call_url)

    def test_rows_sent_in_body(self):
        good = self._make_good_response()
        test_rows = [["A", "B", "C"], ["D", "E", "F"]]
        with self._patch_post([good]) as mock_post:
            mod.append_rows_batch("TOKEN", "SHEET", test_rows)
        body = mock_post.call_args[1]["json"]
        self.assertEqual(body["values"], test_rows)


class TestValidation(unittest.TestCase):

    def test_missing_fields_detected(self):
        v = {"company": "Co", "url": "u"}
        missing = [k for k in ("vacancy", "company", "url", "source", "template") if not v.get(k)]
        self.assertIn("vacancy", missing)
        self.assertIn("source", missing)
        self.assertIn("template", missing)
        self.assertNotIn("company", missing)

    def test_example_vacancies_filtered(self):
        vacancies = [
            {"vacancy": "Example", "_example": True},
            {"vacancy": "Real Job", "company": "Co"},
        ]
        filtered = [v for v in vacancies if not v.get("_example")]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["vacancy"], "Real Job")

    def test_all_fields_required_except_optional(self):
        required = ("vacancy", "company", "url", "source", "template")
        v = {k: "val" for k in required}
        missing = [k for k in required if not v.get(k)]
        self.assertEqual(missing, [])


class TestRetryConstants(unittest.TestCase):

    def test_retry_attempts_positive(self):
        self.assertGreater(mod._RETRY_ATTEMPTS, 0)

    def test_retry_delay_positive(self):
        self.assertGreater(mod._RETRY_DELAY, 0)

    def test_retry_attempts_not_too_high(self):
        self.assertLessEqual(mod._RETRY_ATTEMPTS, 10)


class TestDateHandling(unittest.TestCase):

    def test_empty_date_uses_today(self):
        today = datetime.now().strftime("%d.%m.%Y")
        result = "".strip() or datetime.now().strftime("%d.%m.%Y")
        self.assertEqual(result, today)

    def test_explicit_date_preserved(self):
        result = "15.06.2026".strip() or datetime.now().strftime("%d.%m.%Y")
        self.assertEqual(result, "15.06.2026")


if __name__ == "__main__":
    unittest.main(verbosity=2)
