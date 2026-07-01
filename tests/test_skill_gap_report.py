#!/usr/bin/env python3
"""
test_skill_gap_report.py -- автотесты для skill_gap_report.py
Запуск: python test_skill_gap_report.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
import importlib.util
import pathlib
import os

# Mock externals
class FakeRequestException(Exception):
    pass

fake_requests = MagicMock()
fake_requests.RequestException = FakeRequestException
sys.modules["requests"] = fake_requests

for mod_name in [
    "google", "google.oauth2", "google.oauth2.service_account",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "dotenv",
]:
    sys.modules.setdefault(mod_name, MagicMock())

spec = importlib.util.spec_from_file_location(
    "skill_gap_report",
    pathlib.Path(__file__).parent / "skill_gap_report.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestParseGaps(unittest.TestCase):
    """Тесты parse_gaps() -- разбивка строки пробелов на список"""

    def test_comma_separator(self):
        self.assertEqual(mod.parse_gaps("Docker, Boost, CUDA"),
                         ["Docker", "Boost", "CUDA"])

    def test_semicolon_separator(self):
        self.assertEqual(mod.parse_gaps("Docker; Boost; CUDA"),
                         ["Docker", "Boost", "CUDA"])

    def test_slash_separator(self):
        self.assertEqual(mod.parse_gaps("Docker/Boost/CUDA"),
                         ["Docker", "Boost", "CUDA"])

    def test_newline_separator(self):
        self.assertEqual(mod.parse_gaps("Docker\nBoost\nCUDA"),
                         ["Docker", "Boost", "CUDA"])

    def test_mixed_separators(self):
        result = mod.parse_gaps("Docker, Boost; CUDA/Jenkins")
        self.assertEqual(result, ["Docker", "Boost", "CUDA", "Jenkins"])

    def test_empty_string_returns_empty(self):
        self.assertEqual(mod.parse_gaps(""), [])

    def test_none_returns_empty(self):
        self.assertEqual(mod.parse_gaps(None), [])

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(mod.parse_gaps("   "), [])

    def test_strips_whitespace_from_items(self):
        result = mod.parse_gaps("  Docker  ,  Boost  ")
        self.assertEqual(result, ["Docker", "Boost"])

    def test_ignores_empty_parts(self):
        # двойные разделители
        result = mod.parse_gaps("Docker,,Boost")
        self.assertEqual(result, ["Docker", "Boost"])

    def test_single_item(self):
        self.assertEqual(mod.parse_gaps("Boost.Asio"), ["Boost.Asio"])


class TestAnalyze(unittest.TestCase):
    """Тесты analyze() -- агрегация данных из строк таблицы"""

    def _make_rows(self, data):
        """
        data = список (vacancy, status, skill_gaps)
        Возвращает rows с заголовком и 12 колонками.
        """
        header = ["Вакансия", "Компания", "URL", "Источник", "Шаблон",
                  "F", "G", "H", "Статус", "Комм", "HR", "Пробелы"]
        rows = [header]
        for vac, status, gaps in data:
            row = [""] * 12
            row[0] = vac       # A
            row[8] = status    # I
            row[11] = gaps     # L
            rows.append(row)
        return rows

    def test_counts_total_vacancies(self):
        rows = self._make_rows([
            ("Dev1", "ожидание", "Docker"),
            ("Dev2", "отказ", "Boost"),
            ("Dev3", "ожидание", ""),
        ])
        stats = mod.analyze(rows)
        self.assertEqual(stats["total"], 3)

    def test_counts_vacancies_with_gaps(self):
        rows = self._make_rows([
            ("Dev1", "ожидание", "Docker"),
            ("Dev2", "ожидание", ""),    # пробел пустой -- не считается
            ("Dev3", "отказ", "Boost"),
        ])
        stats = mod.analyze(rows)
        self.assertEqual(stats["with_gaps"], 2)

    def test_gap_counter_aggregates_correctly(self):
        rows = self._make_rows([
            ("Dev1", "ожидание", "Docker, Boost"),
            ("Dev2", "ожидание", "Docker"),
            ("Dev3", "ожидание", "Boost"),
        ])
        stats = mod.analyze(rows)
        self.assertEqual(stats["gap_counter"]["Docker"], 2)
        self.assertEqual(stats["gap_counter"]["Boost"], 2)

    def test_rejection_gap_counted(self):
        rows = self._make_rows([
            ("Dev1", "отказ", "Docker"),
            ("Dev2", "ожидание", "Docker"),
        ])
        stats = mod.analyze(rows)
        self.assertEqual(stats["rejection_gap_counter"]["Docker"], 1)
        self.assertEqual(stats["gap_rejection_map"]["Docker"]["rejected"], 1)
        self.assertEqual(stats["gap_rejection_map"]["Docker"]["total"], 2)

    def test_rejection_status_variants(self):
        """Разные формулировки отказа должны считаться"""
        rows = self._make_rows([
            ("Dev1", "Отказ", "Docker"),
            ("Dev2", "отказали", "Docker"),
            ("Dev3", "rejected", "Docker"),
        ])
        stats = mod.analyze(rows)
        self.assertEqual(stats["rejection_gap_counter"]["Docker"], 3)

    def test_empty_rows_returns_zeros(self):
        rows = [["header1", "header2"]]  # только заголовок
        stats = mod.analyze(rows)
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["with_gaps"], 0)
        self.assertEqual(len(stats["gap_counter"]), 0)

    def test_skips_header_row(self):
        rows = self._make_rows([("Dev1", "ожидание", "Docker")])
        # rows[0] -- заголовок, rows[1] -- данные
        stats = mod.analyze(rows)
        self.assertEqual(stats["total"], 1)

    def test_row_without_vacancy_name_skipped(self):
        header = ["Вакансия"] + [""] * 11
        empty_row = [""] * 12   # нет названия вакансии
        real_row = ["Dev1"] + [""] * 7 + ["ожидание"] + [""] + [""] + ["Docker"]
        rows = [header, empty_row, real_row]
        stats = mod.analyze(rows)
        self.assertEqual(stats["total"], 1)

    def test_short_row_handled_safely(self):
        """Строка короче 12 колонок -- не должно быть IndexError"""
        rows = [["Вакансия", "Компания"], ["Dev1", "Co"]]
        try:
            mod.analyze(rows)
        except IndexError:
            self.fail("analyze() выбросил IndexError на короткой строке")


class TestFormatReport(unittest.TestCase):
    """Тесты format_report() -- форматирование вывода"""

    def _make_stats(self, gap_counter=None, rejection_gap=None, total=10, with_gaps=5):
        from collections import Counter, defaultdict
        gc = Counter(gap_counter or {})
        rc = Counter(rejection_gap or {})
        grm = defaultdict(lambda: {"total": 0, "rejected": 0})
        for skill, cnt in gc.items():
            grm[skill]["total"] = cnt
        for skill, cnt in rc.items():
            grm[skill]["rejected"] = cnt
        return {
            "total": total,
            "with_gaps": with_gaps,
            "gap_counter": gc,
            "rejection_gap_counter": rc,
            "gap_rejection_map": grm,
        }

    def test_no_data_message_when_empty(self):
        stats = self._make_stats(gap_counter={}, total=5, with_gaps=0)
        report = mod.format_report(stats)
        self.assertIn("пока нет", report.lower())

    def test_header_present(self):
        stats = self._make_stats({"Docker": 3}, total=10, with_gaps=5)
        report = mod.format_report(stats)
        self.assertIn("ПРОБЕЛОВ", report)

    def test_top_skills_shown(self):
        stats = self._make_stats({"Docker": 5, "Boost": 3, "CUDA": 2}, total=10, with_gaps=8)
        report = mod.format_report(stats)
        self.assertIn("Docker", report)
        self.assertIn("Boost", report)

    def test_total_count_shown(self):
        stats = self._make_stats({"Docker": 1}, total=42, with_gaps=10)
        report = mod.format_report(stats)
        self.assertIn("42", report)

    def test_rejection_section_when_has_rejections(self):
        stats = self._make_stats(
            {"Docker": 3},
            rejection_gap={"Docker": 2},
            total=10, with_gaps=5,
        )
        report = mod.format_report(stats)
        self.assertIn("ОТКАЗ", report.upper())

    def test_top_n_limit(self):
        # 20 скиллов, но top_n=3
        gaps = {f"Skill{i}": i for i in range(20, 0, -1)}
        stats = self._make_stats(gaps, total=50, with_gaps=20)
        report = mod.format_report(stats, top_n=3)
        # Должно быть не больше 3 скиллов в таблице
        top3 = ["Skill20", "Skill19", "Skill18"]
        for s in top3:
            self.assertIn(s, report)
        # Skill1 (самый редкий) не должен быть
        self.assertNotIn("Skill1\n", report + "\n")


class TestSendTelegram(unittest.TestCase):
    """Тест send_telegram() -- проверка fallback при пустых токенах"""

    def test_no_tokens_prints_warning_does_not_raise(self):
        with patch.object(mod, "TG_BOT_TOKEN", ""), \
             patch.object(mod, "TG_CHAT_ID", ""):
            # Не должно выбрасывать исключение
            try:
                mod.send_telegram("test message")
            except Exception as e:
                self.fail(f"send_telegram выбросил исключение без токенов: {e}")

    def test_with_tokens_calls_requests_post(self):
        fake_resp = MagicMock()
        fake_resp.ok = True
        with patch.object(mod, "TG_BOT_TOKEN", "TOKEN"), \
             patch.object(mod, "TG_CHAT_ID", "12345"), \
             patch.object(fake_requests, "post", return_value=fake_resp) as mock_post:
            mod.send_telegram("test")
        mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
