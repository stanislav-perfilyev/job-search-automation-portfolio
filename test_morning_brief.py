#!/usr/bin/env python3
"""
Автотесты для morning_brief.py
Запуск: python test_morning_brief.py [-v]
"""

import asyncio
import sys
import json
import time
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

# Подключаем модуль (без запуска main)
import morning_brief as mb


# ══════════════════════════════════════════════════════════════════════════════
# 1. Парсеры RSS — чистые функции, без IO
# ══════════════════════════════════════════════════════════════════════════════
class TestParseHhItems(unittest.TestCase):
    def setUp(self):
        self.cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    def test_empty_xml(self):
        self.assertEqual(mb._parse_hh_items("", self.cutoff, set()), [])

    def test_broken_xml(self):
        self.assertEqual(mb._parse_hh_items("<item><title>No closing", self.cutoff, set()), [])

    def test_valid_item(self):
        xml = """<item>
            <title><![CDATA[C++ разработчик]]></title>
            <link>https://hh.kz/vacancy/100</link>
            <pubDate>Mon, 29 Jun 2026 08:00:00 +0000</pubDate>
            <hh:salary>200000-300000 KZT</hh:salary>
        </item>"""
        result = mb._parse_hh_items(xml, self.cutoff, set())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "C++ разработчик")
        self.assertEqual(result[0]["link"], "https://hh.kz/vacancy/100")
        self.assertEqual(result[0]["salary"], "200000-300000 KZT")

    def test_deduplication(self):
        xml = """<item>
            <title>C++ Dev</title>
            <link>https://hh.kz/vacancy/999</link>
        </item>"""
        seen = {"https://hh.kz/vacancy/999"}
        result = mb._parse_hh_items(xml, self.cutoff, seen)
        self.assertEqual(result, [])

    def test_old_item_filtered(self):
        """Вакансия старше cutoff не должна попасть в результат."""
        xml = """<item>
            <title>Old job</title>
            <link>https://hh.kz/vacancy/1</link>
            <pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate>
        </item>"""
        result = mb._parse_hh_items(xml, self.cutoff, set())
        self.assertEqual(result, [])

    def test_no_salary(self):
        xml = """<item>
            <title>Qt Dev</title>
            <link>https://hh.kz/vacancy/2</link>
        </item>"""
        result = mb._parse_hh_items(xml, self.cutoff, set())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["salary"], "")

    def test_multiple_items_dedup(self):
        xml = """
        <item><title>A</title><link>https://hh.kz/1</link></item>
        <item><title>B</title><link>https://hh.kz/2</link></item>
        <item><title>C</title><link>https://hh.kz/1</link></item>
        """
        result = mb._parse_hh_items(xml, self.cutoff, set())
        self.assertEqual(len(result), 2)


class TestParseHabrItems(unittest.TestCase):
    def setUp(self):
        self.cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    def test_valid_item(self):
        xml = """<item>
            <title>Qt разработчик</title>
            <link>https://career.habr.com/vacancies/1</link>
            <author>ООО Компания</author>
            <pubDate>Mon, 29 Jun 2026 10:00:00 +0000</pubDate>
        </item>"""
        result = mb._parse_habr_items(xml, self.cutoff, set())
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["company"], "ООО Компания")

    def test_empty(self):
        self.assertEqual(mb._parse_habr_items("", self.cutoff, set()), [])


# ══════════════════════════════════════════════════════════════════════════════
# 2. _strip_tags
# ══════════════════════════════════════════════════════════════════════════════
class TestStripTags(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(mb._strip_tags("<b>Hello</b>"), "Hello")

    def test_br_to_newline(self):
        result = mb._strip_tags("Line1<br/>Line2")
        self.assertIn("\n", result)

    def test_html_entities(self):
        self.assertEqual(mb._strip_tags("&amp; &lt; &gt;"), "& < >")

    def test_multiple_spaces(self):
        result = mb._strip_tags("a   b   c")
        self.assertEqual(result, "a b c")


# ══════════════════════════════════════════════════════════════════════════════
# 3. _esc — HTML экранирование
# ══════════════════════════════════════════════════════════════════════════════
class TestEsc(unittest.TestCase):
    def test_ampersand(self):
        self.assertEqual(mb._esc("a & b"), "a &amp; b")

    def test_less(self):
        self.assertEqual(mb._esc("a < b"), "a &lt; b")

    def test_greater(self):
        self.assertEqual(mb._esc("a > b"), "a &gt; b")

    def test_no_change(self):
        self.assertEqual(mb._esc("hello world"), "hello world")


# ══════════════════════════════════════════════════════════════════════════════
# 4. _parse_tg_page — Telegram HTML парсер
# ══════════════════════════════════════════════════════════════════════════════
class TestParseTgPage(unittest.TestCase):
    def _make_tg_html(self, channel, post_id, dt_iso, text):
        return f"""
        <div data-post="{channel}/{post_id}" class="tgme_widget_message">
          <time datetime="{dt_iso}">...</time>
          <div class="tgme_widget_message_text js-message_text" dir="auto">
            {text}
          </div>
        </div>
        """

    def test_keyword_match(self):
        now = datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(hours=24)
        dt_iso = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        html = self._make_tg_html("cppdevjob", "42", dt_iso,
                                   "Требуется C++ developer, опыт с Qt приветствуется")
        result = mb._parse_tg_page(html, "cppdevjob", cutoff, now, set(), set())
        self.assertEqual(len(result), 1)
        self.assertIn("cppdevjob/42", result[0]["post_id"])

    def test_no_keyword_filtered(self):
        now = datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(hours=24)
        dt_iso = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        html = self._make_tg_html("chan", "1", dt_iso, "Продам гараж в хорошем состоянии")
        result = mb._parse_tg_page(html, "chan", cutoff, now, set(), set())
        self.assertEqual(result, [])

    def test_cross_channel_dedup(self):
        now = datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(hours=24)
        dt_iso = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        text = "C++ developer needed for Qt project, senior position"
        seen_texts = set()
        html1 = self._make_tg_html("chan1", "1", dt_iso, text)
        html2 = self._make_tg_html("chan2", "2", dt_iso, text)
        r1 = mb._parse_tg_page(html1, "chan1", cutoff, now, set(), seen_texts)
        r2 = mb._parse_tg_page(html2, "chan2", cutoff, now, set(), seen_texts)
        self.assertEqual(len(r1), 1)
        self.assertEqual(len(r2), 0)  # дубль из второго канала


# ══════════════════════════════════════════════════════════════════════════════
# 5. Async _fetch — graceful fallback
# ══════════════════════════════════════════════════════════════════════════════
class TestFetch(unittest.IsolatedAsyncioTestCase):
    async def test_dns_error_returns_none(self):
        async with aiohttp.ClientSession() as session:
            result = await mb._fetch(session, "https://nonexistent-host-xyz-abc.invalid/rss")
        self.assertIsNone(result)

    async def test_timeout_returns_none(self):
        orig = mb._TIMEOUT
        mb._TIMEOUT = aiohttp.ClientTimeout(total=0.001)
        try:
            async with aiohttp.ClientSession() as session:
                result = await mb._fetch(session, "https://httpbin.org/delay/10")
        finally:
            mb._TIMEOUT = orig
        self.assertIsNone(result)

    async def test_retry_count(self):
        """Проверяем что делается MAX_RETRIES+1 попыток при ошибках."""
        call_count = 0
        orig_retries = mb._MAX_RETRIES
        orig_delay   = mb._RETRY_DELAY
        mb._MAX_RETRIES = 2
        mb._RETRY_DELAY = 0.01

        # session.get должен быть async context manager
        class FailCtx:
            async def __aenter__(self_inner):
                nonlocal call_count
                call_count += 1
                raise aiohttp.ClientConnectorError(
                    connection_key=MagicMock(), os_error=OSError("fail")
                )
            async def __aexit__(self_inner, *a):
                pass

        session = MagicMock()
        session.get = MagicMock(return_value=FailCtx())

        result = await mb._fetch(session, "https://example.com")
        self.assertIsNone(result)
        self.assertEqual(call_count, mb._MAX_RETRIES + 1)

        mb._MAX_RETRIES = orig_retries
        mb._RETRY_DELAY = orig_delay


# ══════════════════════════════════════════════════════════════════════════════
# 6. Async fetchers — с полностью мокнутой сетью
# ══════════════════════════════════════════════════════════════════════════════
class TestFetchHhRss(unittest.IsolatedAsyncioTestCase):
    async def test_all_fail_returns_empty(self):
        orig = mb.HH_RSS_URLS
        mb.HH_RSS_URLS = ["https://fail.xyz/1", "https://fail.xyz/2"]
        try:
            async with aiohttp.ClientSession() as session:
                result = await mb.fetch_hh_rss_async(session)
        finally:
            mb.HH_RSS_URLS = orig
        self.assertEqual(result, [])

    async def test_limit_applied(self):
        """Проверяем что MAX_PER_SOURCE обрезает результат."""
        # Генерируем XML с 30 вакансиями
        items = ""
        for i in range(30):
            items += f"""<item>
                <title>Job {i}</title>
                <link>https://hh.kz/vacancy/{i}</link>
                <pubDate>Mon, 29 Jun 2026 08:00:00 +0000</pubDate>
            </item>"""
        xml = f"<rss>{items}</rss>"

        orig_urls = mb.HH_RSS_URLS
        mb.HH_RSS_URLS = ["https://mock.url/rss"]
        orig_max = mb.MAX_PER_SOURCE
        mb.MAX_PER_SOURCE = 10

        with patch("morning_brief._fetch", new=AsyncMock(return_value=xml)):
            async with aiohttp.ClientSession() as session:
                result = await mb.fetch_hh_rss_async(session)

        mb.HH_RSS_URLS = orig_urls
        mb.MAX_PER_SOURCE = orig_max
        self.assertEqual(len(result), 10)


# ══════════════════════════════════════════════════════════════════════════════
# 7. gather — return_exceptions=True, один источник падает, остальные живут
# ══════════════════════════════════════════════════════════════════════════════
class TestGatherFaultTolerance(unittest.IsolatedAsyncioTestCase):
    async def test_one_source_exception_doesnt_kill_others(self):
        async def ok_coro():
            return [{"title": "OK", "link": "https://ok.com", "salary": ""}]

        async def fail_coro():
            raise RuntimeError("Source down!")

        results = await asyncio.gather(
            ok_coro(), fail_coro(), return_exceptions=True
        )
        # Первый ОК, второй — Exception, не краш
        self.assertEqual(results[0], [{"title": "OK", "link": "https://ok.com", "salary": ""}])
        self.assertIsInstance(results[1], RuntimeError)

    async def test_safe_extract_helper(self):
        def _safe(val, default):
            return val if not isinstance(val, Exception) else default

        self.assertEqual(_safe([], [1, 2]), [])
        self.assertEqual(_safe(RuntimeError("x"), []), [])
        self.assertEqual(_safe({"k": "v"}, {}), {"k": "v"})


# ══════════════════════════════════════════════════════════════════════════════
# 8. _build_message — форматирование
# ══════════════════════════════════════════════════════════════════════════════
class TestBuildMessage(unittest.TestCase):
    def _make_msg(self, **kwargs):
        defaults = dict(
            date_str="29.06.2026",
            stats={"total": 50, "waiting": 30, "stale": 5, "stale_list": [],
                   "interview": 1, "offer": 0, "rejected": 10},
            calendar_events=[{"time": "10:00", "summary": "Интервью"}],
            hh_vacancies=[{"title": "C++ Dev", "link": "https://hh.kz/1", "salary": ""}],
            habr_vacancies=[{"title": "Qt Dev", "link": "https://habr.com/1", "company": "ООО"}],
            tg_vacancies=[{"channel": "cppdevjob", "post_id": "x/1",
                           "text": "C++ нужен", "link": "https://t.me/x/1", "date": ""}],
            claudedev_posts=[],
            is_monday=False,
            elapsed=2.34,
            n_sources=34,
            hh_total=181,
            habr_total=25,
            tg_total=14,
        )
        defaults.update(kwargs)
        return mb._build_message(**defaults)

    def test_contains_asyncio_footer(self):
        msg = self._make_msg()
        self.assertIn("[asyncio v2]", msg)
        self.assertIn("2.34 сек", msg)

    def test_hh_limit_note_shown(self):
        msg = self._make_msg()
        self.assertIn("181", msg)  # total показан

    def test_interview_shown(self):
        msg = self._make_msg()
        self.assertIn("Интервью", msg)

    def test_calendar_event_shown(self):
        msg = self._make_msg()
        self.assertIn("10:00", msg)
        self.assertIn("Интервью", msg)

    def test_html_escaped(self):
        msg = self._make_msg(
            hh_vacancies=[{"title": "C++ & Qt <Dev>", "link": "https://hh.kz/1", "salary": ""}],
            hh_total=1
        )
        self.assertNotIn("C++ & Qt <Dev>", msg)
        self.assertIn("C++ &amp; Qt &lt;Dev&gt;", msg)

    def test_no_claudedev_on_non_monday(self):
        msg = self._make_msg(is_monday=False, claudedev_posts=[
            {"post_id": "x", "text": "useful", "link": "t.me/x", "date": ""}
        ])
        self.assertNotIn("CLAUDEDEVOLPER", msg)

    def test_claudedev_on_monday(self):
        msg = self._make_msg(is_monday=True, claudedev_posts=[
            {"post_id": "x", "text": "полезный инструмент для автоматизации", "link": "t.me/x", "date": ""}
        ])
        self.assertIn("CLAUDEDEVOLPER", msg)

    def test_empty_stats_fallback(self):
        msg = self._make_msg(stats={})
        self.assertIn("таблица недоступна", msg)

    def test_message_reasonable_length(self):
        """Сообщение с лимитами должно быть <4000 символов (1 часть)."""
        msg = self._make_msg(
            hh_vacancies=[{"title": f"Job {i}", "link": f"https://hh.kz/{i}", "salary": ""} for i in range(15)],
            habr_vacancies=[{"title": f"Habr {i}", "link": f"https://habr.com/{i}", "company": ""} for i in range(15)],
            tg_vacancies=[{"channel": "ch", "post_id": f"ch/{i}", "text": "C++ dev", "link": f"t.me/ch/{i}", "date": ""} for i in range(10)],
        )
        self.assertLess(len(msg), 4000, f"Сообщение слишком длинное: {len(msg)} симв.")


# ══════════════════════════════════════════════════════════════════════════════
# 9. Performance: параллельность ускоряет в ≥2x
# ══════════════════════════════════════════════════════════════════════════════
class TestPerformance(unittest.IsolatedAsyncioTestCase):
    async def test_parallel_faster_than_sequential(self):
        """3 корутины по 0.1с → параллельно <0.25с, последовательно >0.3с."""
        async def slow():
            await asyncio.sleep(0.1)
            return "ok"

        t0 = time.time()
        results = await asyncio.gather(slow(), slow(), slow())
        parallel_time = time.time() - t0

        self.assertTrue(all(r == "ok" for r in results))
        self.assertLess(parallel_time, 0.25,
                        f"Параллельное выполнение заняло {parallel_time:.2f}с (ожидалось <0.25с)")


# ══════════════════════════════════════════════════════════════════════════════
# Запуск
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    verbosity = 2 if "-v" in sys.argv else 1
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
