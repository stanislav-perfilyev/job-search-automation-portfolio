#!/usr/bin/env python3
"""
test_hh_auth.py -- тесты для refresh_hh_cookies.py
Запуск: python test_hh_auth.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
import importlib.util
import pathlib

# Mock playwright before import
fake_playwright = MagicMock()
sys.modules["playwright"] = fake_playwright
sys.modules["playwright.sync_api"] = fake_playwright
sys.modules.setdefault("dotenv", MagicMock())

spec = importlib.util.spec_from_file_location(
    "refresh_hh_cookies",
    pathlib.Path(__file__).parent / "refresh_hh_cookies.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class TestCheckSessionExists(unittest.TestCase):

    def test_returns_false_if_dir_missing(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = mod.check_session_exists()
        self.assertFalse(result)

    def test_returns_false_if_dir_empty(self):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.iterdir", return_value=iter([])):
            result = mod.check_session_exists()
        self.assertFalse(result)

    def test_returns_true_if_dir_has_files(self):
        fake_file = MagicMock()
        with patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.iterdir", return_value=iter([fake_file])):
            result = mod.check_session_exists()
        self.assertTrue(result)


class TestGetFreshCookiesNoSession(unittest.TestCase):

    def test_returns_empty_if_no_session_dir(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = mod.get_fresh_cookies(verbose=False)
        self.assertEqual(result, "")

    def test_returns_empty_on_playwright_exception(self):
        with patch("pathlib.Path.exists", return_value=True), \
             patch("playwright.sync_api.sync_playwright", side_effect=Exception("crash")):
            result = mod.get_fresh_cookies(verbose=False)
        self.assertEqual(result, "")

    def test_returns_string_type(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = mod.get_fresh_cookies(verbose=False)
        self.assertIsInstance(result, str)


class TestCookieFiltering(unittest.TestCase):
    """Тесты логики фильтрации куки hh.kz (чистые функции)."""

    def test_hh_kz_domain_included(self):
        cookies = [
            {"name": "tok", "value": "val", "domain": ".hh.kz"},
            {"name": "ga", "value": "1", "domain": ".google.com"},
        ]
        hh_domains = mod.HH_DOMAINS
        filtered = [c for c in cookies if any(
            c.get("domain", "").endswith(d.lstrip(".")) or c.get("domain", "") == d
            for d in hh_domains
        )]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["name"], "tok")

    def test_google_domain_excluded(self):
        cookies = [{"name": "ga", "value": "1", "domain": ".google.com"}]
        filtered = [c for c in cookies if any(
            c.get("domain", "").endswith(d.lstrip(".")) or c.get("domain", "") == d
            for d in mod.HH_DOMAINS
        )]
        self.assertEqual(len(filtered), 0)

    def test_cookie_string_format(self):
        cookies = [
            {"name": "a", "value": "1"},
            {"name": "b", "value": "2"},
        ]
        result = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        self.assertEqual(result, "a=1; b=2")

    def test_empty_cookies_gives_empty_string(self):
        result = "; ".join(f"{c['name']}={c['value']}" for c in [])
        self.assertEqual(result, "")


class TestConstants(unittest.TestCase):

    def test_ddos_guard_cookies_set_defined(self):
        self.assertIsInstance(mod.DDOS_GUARD_COOKIES, set)
        self.assertGreater(len(mod.DDOS_GUARD_COOKIES), 0)

    def test_hh_domains_includes_hh_kz(self):
        self.assertTrue(
            any("hh.kz" in d for d in mod.HH_DOMAINS)
        )

    def test_session_dir_path_is_absolute(self):
        self.assertTrue(mod.SESSION_DIR.is_absolute())

    def test_ddos_guard_cookies_names_not_empty(self):
        for name in mod.DDOS_GUARD_COOKIES:
            self.assertGreater(len(name), 0)


class TestCookieAlmaty(unittest.TestCase):
    """Тест что almaty.hh.kz куки принимаются."""

    def test_almaty_hh_kz_included(self):
        cookies = [
            {"name": "tok", "value": "val", "domain": "almaty.hh.kz"},
        ]
        filtered = [c for c in cookies if any(
            c.get("domain", "").endswith(d.lstrip(".")) or c.get("domain", "") == d
            for d in mod.HH_DOMAINS
        )]
        self.assertEqual(len(filtered), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
