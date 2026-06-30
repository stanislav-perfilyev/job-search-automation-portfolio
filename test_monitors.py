#!/usr/bin/env python3
"""
test_monitors.py -- тесты для telegram_monitor.py, negotiations_monitor_local.py,
                    upwork_email_monitor.py
Запуск: python test_monitors.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open
import importlib.util
import pathlib
import os
from datetime import datetime, timezone, timedelta

# ============================================================
# Общие моки
# ============================================================

class FakeRequestException(Exception): pass
fake_requests = MagicMock()
fake_requests.RequestException = FakeRequestException
sys.modules["requests"] = fake_requests

for m in [
    "google", "google.oauth2", "google.oauth2.service_account",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "dotenv", "win32crypt", "win32file", "win32con",
    "cryptography", "cryptography.hazmat", "cryptography.hazmat.primitives",
    "cryptography.hazmat.primitives.ciphers",
    "cryptography.hazmat.primitives.ciphers.aead",
    "cryptography.hazmat.primitives.serialization",
    "cryptography.hazmat.primitives.asymmetric",
    "cryptography.hazmat.primitives.asymmetric.padding",
    "cryptography.hazmat.primitives.hashes",
    "playwright", "playwright.sync_api",
]:
    sys.modules.setdefault(m, MagicMock())

def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, pathlib.Path(__file__).parent / filename
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

tmon = _load("telegram_monitor",          "telegram_monitor.py")
upmon = _load("upwork_email_monitor",     "upwork_email_monitor.py")


# ============================================================
# telegram_monitor.py
# ============================================================

class TestStripTags(unittest.TestCase):

    def test_removes_html_tags(self):
        self.assertEqual(tmon.strip_tags("<b>Hello</b>"), "Hello")

    def test_br_becomes_newline(self):
        result = tmon.strip_tags("Line1<br>Line2")
        self.assertIn("Line1", result)
        self.assertIn("Line2", result)

    def test_unescapes_html_entities(self):
        result = tmon.strip_tags("&amp; &lt; &gt;")
        self.assertIn("&", result)
        self.assertIn("<", result)

    def test_collapses_whitespace(self):
        result = tmon.strip_tags("  hello   world  ")
        self.assertNotIn("  ", result)

    def test_strips_outer_whitespace(self):
        result = tmon.strip_tags("  text  ")
        self.assertEqual(result, "text")

    def test_empty_string(self):
        self.assertEqual(tmon.strip_tags(""), "")


class TestIsAlreadyApplied(unittest.TestCase):

    def test_detects_company_in_text(self):
        self.assertTrue(tmon.is_already_applied(
            "Вакансия от компании Яндекс на C++ разработчика",
            {"яндекс"}
        ))

    def test_returns_false_if_not_applied(self):
        self.assertFalse(tmon.is_already_applied(
            "Вакансия C++ в Google",
            {"яндекс"}
        ))

    def test_returns_false_for_empty_companies(self):
        self.assertFalse(tmon.is_already_applied("any text", set()))

    def test_case_insensitive(self):
        self.assertTrue(tmon.is_already_applied(
            "ЯНДЕКС ищет разработчика",
            {"яндекс"}
        ))

    def test_short_company_name_ignored(self):
        # Имена < 4 символов не должны фильтровать
        self.assertFalse(tmon.is_already_applied(
            "Компания ABC ищет разработчика",
            {"abc"}
        ))


class TestParsePosts(unittest.TestCase):

    def _make_html(self, post_id, dt_str, text):
        return (
            f'data-post="{post_id}" '
            f'datetime="{dt_str}" '
            f'class="tgme_widget_message_text js-message_text">'
            f'{text}'
            f'</div> </div>'
        )

    def _now(self):
        return datetime.now(tz=timezone.utc)

    def test_keyword_match_found(self):
        now = self._now()
        dt = (now - timedelta(hours=1)).isoformat()
        html = self._make_html("chan/1", dt, "C++ developer needed")
        posts = tmon.parse_posts("chan", html, now, set(), set())
        self.assertEqual(len(posts), 1)

    def test_no_keyword_filtered(self):
        now = self._now()
        dt = (now - timedelta(hours=1)).isoformat()
        html = self._make_html("chan/2", dt, "Java developer needed")
        posts = tmon.parse_posts("chan", html, now, set(), set())
        self.assertEqual(len(posts), 0)

    def test_old_post_filtered(self):
        now = self._now()
        dt = (now - timedelta(hours=100)).isoformat()
        html = self._make_html("chan/3", dt, "C++ developer needed")
        posts = tmon.parse_posts("chan", html, now, set(), set())
        self.assertEqual(len(posts), 0)

    def test_already_seen_id_skipped(self):
        now = self._now()
        dt = (now - timedelta(hours=1)).isoformat()
        html = self._make_html("chan/4", dt, "C++ developer needed")
        seen = {"chan/4"}
        posts = tmon.parse_posts("chan", html, now, seen, set())
        self.assertEqual(len(posts), 0)

    def test_cross_channel_dedup(self):
        now = self._now()
        dt = (now - timedelta(hours=1)).isoformat()
        # Одинаковый текст в двух каналах
        text = "C++ developer needed urgent vacancy"
        html1 = self._make_html("chan1/1", dt, text)
        html2 = self._make_html("chan2/1", dt, text)
        seen_texts = set()
        seen_ids = set()
        posts1 = tmon.parse_posts("chan1", html1, now, seen_ids, set(), seen_texts)
        posts2 = tmon.parse_posts("chan2", html2, now, seen_ids, set(), seen_texts)
        total = len(posts1) + len(posts2)
        self.assertEqual(total, 1, "Дублирующий пост должен фильтроваться")

    def test_post_has_link(self):
        now = self._now()
        dt = (now - timedelta(hours=1)).isoformat()
        html = self._make_html("mychannel/42", dt, "C++ developer")
        posts = tmon.parse_posts("mychannel", html, now, set(), set())
        if posts:
            self.assertIn("t.me/mychannel/42", posts[0]["link"])


class TestTelegramMonitorState(unittest.TestCase):

    def test_load_state_returns_empty_if_no_file(self):
        with patch("pathlib.Path.exists", return_value=False):
            state = tmon.load_state()
        self.assertIn("seen", state)
        self.assertEqual(state["seen"], {})

    def test_save_state_prunes_old_entries(self):
        import json
        now = datetime.now(tz=timezone.utc)
        old_ts = (now - timedelta(days=60)).isoformat()
        new_ts = now.isoformat()
        state = {"seen": {"old_post": old_ts, "new_post": new_ts}}
        saved = {}
        def fake_dump(data, f, **kw):
            saved.update(data)
        with patch("builtins.open", mock_open()), \
             patch("json.dump", fake_dump):
            tmon.save_state(state, now)
        self.assertNotIn("old_post", saved.get("seen", {}))
        self.assertIn("new_post", saved.get("seen", {}))


# ============================================================
# upwork_email_monitor.py
# ============================================================

class TestDecodeStr(unittest.TestCase):

    def test_plain_ascii(self):
        self.assertEqual(upmon.decode_str("Hello World"), "Hello World")

    def test_encoded_utf8(self):
        # =?utf-8?b?SGVsbG8=?= = "Hello" in base64
        result = upmon.decode_str("=?utf-8?b?SGVsbG8=?=")
        self.assertEqual(result, "Hello")


class TestClassifyEvent(unittest.TestCase):

    def test_contract_started(self):
        result = upmon.classify_event("Your contract has started")
        self.assertIsNotNone(result)
        label, priority = result
        self.assertEqual(priority, 1)

    def test_offer_received(self):
        label, priority = upmon.classify_event("A new offer has been extended")
        self.assertEqual(priority, 1)

    def test_new_message(self):
        label, priority = upmon.classify_event("You have a new message")
        self.assertEqual(priority, 2)

    def test_proposal_viewed(self):
        label, priority = upmon.classify_event("Viewed your proposal")
        self.assertEqual(priority, 3)

    def test_shortlisted(self):
        label, priority = upmon.classify_event("You have been shortlisted")
        self.assertEqual(priority, 2)

    def test_unrelated_returns_none(self):
        result = upmon.classify_event("Your weekly digest is ready")
        self.assertIsNone(result)

    def test_case_insensitive(self):
        result = upmon.classify_event("CONTRACT HAS STARTED")
        self.assertIsNotNone(result)


class TestIsUpworkSender(unittest.TestCase):

    def test_upwork_domain(self):
        self.assertTrue(upmon.is_upwork_sender("Upwork <noreply@upwork.com>"))

    def test_notifications_subdomain(self):
        self.assertTrue(upmon.is_upwork_sender("notifications@upwork.com"))

    def test_non_upwork(self):
        self.assertFalse(upmon.is_upwork_sender("info@gmail.com"))

    def test_case_insensitive(self):
        self.assertTrue(upmon.is_upwork_sender("NOREPLY@UPWORK.COM"))


class TestFormatUpworkMessage(unittest.TestCase):

    def _event(self, label="🎉 КОНТРАКТ НАЧАТ", priority=1, hours_ago=1):
        from datetime import timezone
        dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        return {
            "subject": "Your contract has started",
            "from": "noreply@upwork.com",
            "date": dt,
            "label": label,
            "priority": priority,
        }

    def test_message_has_label(self):
        msg = upmon.format_message(self._event())
        self.assertIn("КОНТРАКТ НАЧАТ", msg)

    def test_message_has_subject(self):
        msg = upmon.format_message(self._event())
        self.assertIn("Your contract has started", msg)

    def test_message_has_html_tags(self):
        msg = upmon.format_message(self._event())
        self.assertIn("<b>", msg)

    def test_message_has_upwork_links(self):
        msg = upmon.format_message(self._event())
        self.assertIn("upwork.com", msg)

    def test_no_date_handled(self):
        ev = self._event()
        ev["date"] = None
        try:
            msg = upmon.format_message(ev)
        except Exception as e:
            self.fail(f"format_message с date=None выбросил: {e}")


# ============================================================
# negotiations_monitor_local.py -- только чистые функции
# ============================================================

# Загружаем отдельно т.к. много windows-специфичных импортов
try:
    nmon = _load("negotiations_monitor_local", "negotiations_monitor_local.py")

    class TestParseNegotiations(unittest.TestCase):

        def _html_block(self, company, vacancy, tag="viewed", has_test=False, vac_id=None):
            test_html = '<a class="survey-link">Пройти опрос</a>' if has_test else ""
            vac_href = f'href="/vacancy/{vac_id}"' if vac_id else ""
            return (
                f'data-qa="negotiations-item"'
                f'  data-qa="negotiations-item-vacancy" >{vacancy}</data-qa>'
                f'  <span data-qa="negotiations-item-company">{company}</span>'
                f'  <time data-qa="negotiations-item-date">29.06.2026</time>'
                f'  <span data-qa="negotiations-tag negotiations-item-{tag}">tag</span>'
                f'  <a {vac_href} href="/employer/123">Co</a>'
                f'  {test_html}'
            )

        def test_classify_offer(self):
            neg = {"status": "offer", "has_unread": False, "has_test": False}
            self.assertEqual(nmon.classify(neg, is_new=True), "OFFER")

        def test_classify_reject(self):
            neg = {"status": "discard", "has_unread": False, "has_test": False}
            self.assertEqual(nmon.classify(neg, is_new=True), "REJECT")

        def test_classify_needs_reply(self):
            neg = {"status": "viewed", "has_unread": True, "has_test": False}
            self.assertEqual(nmon.classify(neg, is_new=True), "NEEDS_REPLY")

        def test_classify_survey(self):
            neg = {"status": "viewed", "has_unread": False, "has_test": True}
            self.assertEqual(nmon.classify(neg, is_new=True), "SURVEY")

        def test_classify_info(self):
            neg = {"status": "viewed", "has_unread": False, "has_test": False}
            self.assertEqual(nmon.classify(neg, is_new=True), "INFO")

        def test_find_changes_new_item(self):
            old_state = {"negotiations": {}}
            current = [{
                "key": "Co|Dev",
                "company": "Co", "vacancy": "Dev",
                "status": "viewed", "has_unread": False, "has_test": False,
                "date": "", "url": "", "vacancy_page_url": "",
            }]
            changes = nmon.find_changes(old_state, current)
            self.assertEqual(len(changes), 1)

        def test_find_changes_status_change(self):
            old_state = {"negotiations": {
                "Co|Dev": {"status": "viewed", "date": "", "has_unread": False, "has_test": False}
            }}
            current = [{
                "key": "Co|Dev", "company": "Co", "vacancy": "Dev",
                "status": "discard", "has_unread": False, "has_test": False,
                "date": "", "url": "", "vacancy_page_url": "",
            }]
            changes = nmon.find_changes(old_state, current)
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0][0], "REJECT")

        def test_find_changes_no_change(self):
            old_state = {"negotiations": {
                "Co|Dev": {"status": "viewed", "date": "", "has_unread": False, "has_test": False}
            }}
            current = [{
                "key": "Co|Dev", "company": "Co", "vacancy": "Dev",
                "status": "viewed", "has_unread": False, "has_test": False,
                "date": "", "url": "", "vacancy_page_url": "",
            }]
            changes = nmon.find_changes(old_state, current)
            self.assertEqual(len(changes), 0)

    class TestLoadSaveState(unittest.TestCase):

        def test_load_state_missing_file(self):
            with patch("pathlib.Path.exists", return_value=False):
                state = nmon.load_state()
            self.assertIn("negotiations", state)
            self.assertEqual(state["negotiations"], {})

        def test_save_state_writes_all_negotiations(self):
            import json
            state = {}
            current = [{
                "key": "Co|Dev", "status": "viewed",
                "date": "", "has_unread": False, "has_test": False,
            }]
            written = {}
            def fake_dump(data, f, **kw):
                written.update(data)
            with patch("builtins.open", mock_open()), \
                 patch("json.dump", fake_dump):
                nmon.save_state(state, current, "29.06.2026 10:00")
            self.assertIn("Co|Dev", written["negotiations"])

except Exception as e:
    print(f"[SKIP] negotiations_monitor_local.py не загружен: {e}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
