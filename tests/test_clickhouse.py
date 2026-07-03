"""
tests/test_clickhouse.py — тесты ClickHouseWriter и analytics query-функций.

Не требует реального ClickHouse: используется unittest.mock.
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

# ── ClickHouseWriter тесты ────────────────────────────────────────────────

class TestClickHouseWriterGraceful:
    """Тесты graceful-режима: ошибки не поднимаются."""

    def test_no_url_graceful(self):
        """Без CLICKHOUSE_URL writer создаётся без ошибки."""
        with patch.dict(os.environ, {"CLICKHOUSE_URL": ""}):
            from db.clickhouse_writer import ClickHouseWriter
            w = ClickHouseWriter()
            assert w._client is None

    def test_log_event_no_client_returns_false(self):
        """log_vacancy_event без клиента → False, не exception."""
        with patch.dict(os.environ, {"CLICKHOUSE_URL": ""}):
            from db.clickhouse_writer import ClickHouseWriter
            w = ClickHouseWriter()
            result = w.log_vacancy_event(
                vacancy_id=1, action="applied", source="hh.kz", company="Test"
            )
            assert result is False

    def test_log_skill_gaps_no_client_returns_false(self):
        """log_skill_gaps без клиента → False."""
        with patch.dict(os.environ, {"CLICKHOUSE_URL": ""}):
            from db.clickhouse_writer import ClickHouseWriter
            w = ClickHouseWriter()
            assert w.log_skill_gaps(["Qt", "eBPF"]) is False

    def test_health_check_no_client(self):
        """health_check без клиента → строка с описанием проблемы."""
        with patch.dict(os.environ, {"CLICKHOUSE_URL": ""}):
            from db.clickhouse_writer import ClickHouseWriter
            w = ClickHouseWriter()
            result = w.health_check()
            assert len(result) > 0  # не пустая строка = проблема

    def test_context_manager(self):
        """ClickHouseWriter используется как контекстный менеджер."""
        with patch.dict(os.environ, {"CLICKHOUSE_URL": ""}):
            from db.clickhouse_writer import ClickHouseWriter
            with ClickHouseWriter() as w:
                assert w._client is None


class TestClickHouseWriterWithMockClient:
    """Тесты с подменённым клиентом через unittest.mock."""

    def _make_writer_with_mock_client(self):
        """Создать writer с mocked клиентом, минуя реальное подключение."""
        with patch.dict(os.environ, {"CLICKHOUSE_URL": ""}):
            from db.clickhouse_writer import ClickHouseWriter
            w = ClickHouseWriter()
        mock_client = MagicMock()
        w._client = mock_client
        return w, mock_client

    def test_log_vacancy_event_calls_insert(self):
        """log_vacancy_event вызывает insert с правильными параметрами."""
        from db.clickhouse_writer import ClickHouseWriter
        w, mock_client = self._make_writer_with_mock_client()

        result = w.log_vacancy_event(
            vacancy_id=42,
            action="applied",
            source="hh.kz",
            company="Yandex",
            skill_gaps=["Qt", "Docker"],
            event_date=date(2026, 7, 3),
        )

        assert result is True
        mock_client.insert.assert_called_once()
        call_args = mock_client.insert.call_args
        table = call_args[0][0]
        rows  = call_args[0][1]
        assert table == "analytics.vacancy_events"
        assert len(rows) == 1
        row = rows[0]
        assert row["vacancy_id"] == 42
        assert row["action"] == "applied"
        assert row["source"] == "hh.kz"
        assert row["company"] == "Yandex"
        assert row["skill_gaps"] == ["Qt", "Docker"]

    def test_log_skill_gaps_calls_insert(self):
        """log_skill_gaps вставляет по одной строке на скилл."""
        from db.clickhouse_writer import ClickHouseWriter
        w, mock_client = self._make_writer_with_mock_client()

        result = w.log_skill_gaps(["Qt", "eBPF", "ClickHouse"], event_date=date(2026, 7, 3))

        assert result is True
        mock_client.insert.assert_called_once()
        rows = mock_client.insert.call_args[0][1]
        assert len(rows) == 3
        skills_inserted = {r["skill"] for r in rows}
        assert skills_inserted == {"Qt", "eBPF", "ClickHouse"}
        # Все строки с одним месяцем
        months = {r["month"] for r in rows}
        assert len(months) == 1

    def test_log_event_graceful_on_insert_error(self):
        """Insert exception → graceful=True → returns False, не поднимает."""
        from db.clickhouse_writer import ClickHouseWriter
        w, mock_client = self._make_writer_with_mock_client()
        mock_client.insert.side_effect = RuntimeError("CH недоступен")

        result = w.log_vacancy_event(
            vacancy_id=1, action="applied", source="hh.kz", company="Test"
        )
        assert result is False

    def test_health_check_ok(self):
        """health_check → пустая строка при SELECT 1 = (1,)."""
        from db.clickhouse_writer import ClickHouseWriter
        w, mock_client = self._make_writer_with_mock_client()
        mock_client.query.return_value = MagicMock(result_rows=[(1,)])

        assert w.health_check() == ""

    def test_health_check_error(self):
        """health_check → описание ошибки при исключении."""
        from db.clickhouse_writer import ClickHouseWriter
        w, mock_client = self._make_writer_with_mock_client()
        mock_client.query.side_effect = ConnectionError("timeout")

        result = w.health_check()
        assert "timeout" in result or "недоступен" in result

    def test_safe_url_hides_password(self):
        """_safe_url не включает пароль в строку."""
        from db.clickhouse_writer import ClickHouseWriter
        url = "clickhouse://user:supersecret@localhost:8123/analytics"
        safe = ClickHouseWriter._safe_url(url)
        assert "supersecret" not in safe
        assert "localhost" in safe


# ── Analytics query-функции тесты ────────────────────────────────────────

class TestAnalyticsQueries:
    """Тесты query-функций из automation/analytics.py с mock клиентом."""

    @staticmethod
    def _mock_client(rows):
        client = MagicMock()
        client.query.return_value = MagicMock(result_rows=rows)
        return client

    def test_top_companies(self):
        from automation.analytics import top_companies
        rows = [("Yandex", 15), ("Kaspersky", 10), ("EPAM", 7)]
        data = top_companies(self._mock_client(rows), days=30)
        assert len(data) == 3
        assert data[0] == {"company": "Yandex", "count": 15}
        assert data[1]["company"] == "Kaspersky"

    def test_top_companies_empty(self):
        from automation.analytics import top_companies
        data = top_companies(self._mock_client([]), days=30)
        assert data == []

    def test_conversion_by_source(self):
        from automation.analytics import conversion_by_source
        rows = [("hh.kz", 100, 20, 5, 60), ("LinkedIn", 30, 10, 3, 15)]
        data = conversion_by_source(self._mock_client(rows))
        assert len(data) == 2
        hh = data[0]
        assert hh["source"] == "hh.kz"
        assert hh["applied"] == 100
        assert hh["offer"] == 5
        assert hh["conv_pct"] == 5.0    # 5/100 * 100

    def test_conversion_zero_applied(self):
        """applied=0 → conv_pct=0.0, не деление на ноль."""
        from automation.analytics import conversion_by_source
        rows = [("LinkedIn", 0, 0, 0, 0)]
        data = conversion_by_source(self._mock_client(rows))
        assert data[0]["conv_pct"] == 0.0

    def test_skill_gap_trends_up(self):
        from automation.analytics import skill_gap_trends
        # (skill, total, prev_month, curr_month)
        rows = [("Qt", 30, 5, 10), ("eBPF", 20, 8, 4), ("Docker", 15, 5, 5)]
        data = skill_gap_trends(self._mock_client(rows), months=3)
        trends = {r["skill"]: r["trend"] for r in data}
        assert trends["Qt"]     == "up"
        assert trends["eBPF"]   == "down"
        assert trends["Docker"] == "stable"

    def test_salary_by_stack(self):
        from automation.analytics import salary_by_stack
        rows = [("Qt", 180000, 12), ("C++", 200000, 25)]
        data = salary_by_stack(self._mock_client(rows))
        assert data[0]["skill"] == "Qt"
        assert data[0]["avg_salary"] == 180000
        assert data[1]["vacancy_count"] == 25

    def test_analytics_error_on_query_fail(self):
        """Ошибка CH → AnalyticsError."""
        from automation.analytics import top_companies, AnalyticsError
        client = MagicMock()
        client.query.side_effect = Exception("CH down")
        with pytest.raises(AnalyticsError):
            top_companies(client, days=30)


# ── FastAPI endpoint тесты ────────────────────────────────────────────────

class TestAnalyticsEndpoints:
    """Тесты FastAPI /analytics/* эндпоинтов с mock ClickHouse."""

    @pytest.fixture(autouse=True)
    def _patch_ch(self, monkeypatch):
        """Подменяем _get_ch_client и analytics query-функции."""
        self._mock_ch = MagicMock()

        import app.routers.analytics as ar
        monkeypatch.setattr(ar, "_get_ch_client", lambda: self._mock_ch)

    def _make_client(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        import app.routers.analytics as ar
        from app.auth import verify_token

        mini_app = FastAPI()

        async def _skip_auth():
            return "test"

        mini_app.include_router(ar.router)
        mini_app.dependency_overrides[verify_token] = _skip_auth
        return TestClient(mini_app, raise_server_exceptions=False)

    def test_top_companies_200(self, monkeypatch):
        import automation.analytics as an
        monkeypatch.setattr(an, "top_companies", lambda c, days: [{"company": "X", "count": 5}])

        client = self._make_client()
        resp = client.get("/analytics/top-companies")
        assert resp.status_code == 200
        assert resp.json()[0]["company"] == "X"

    def test_conversion_200(self, monkeypatch):
        import automation.analytics as an
        monkeypatch.setattr(an, "conversion_by_source", lambda c, source: [
            {"source": "hh.kz", "applied": 10, "interview": 2, "offer": 1, "rejected": 5, "conv_pct": 10.0}
        ])

        client = self._make_client()
        resp = client.get("/analytics/conversion")
        assert resp.status_code == 200
        assert resp.json()[0]["conv_pct"] == 10.0

    def test_skill_trends_200(self, monkeypatch):
        import automation.analytics as an
        monkeypatch.setattr(an, "skill_gap_trends", lambda c, months: [
            {"skill": "Qt", "total": 10, "prev_month": 3, "curr_month": 7, "trend": "up"}
        ])

        client = self._make_client()
        resp = client.get("/analytics/skill-trends")
        assert resp.status_code == 200
        assert resp.json()[0]["trend"] == "up"

    def test_salary_stack_200(self, monkeypatch):
        import automation.analytics as an
        monkeypatch.setattr(an, "salary_by_stack", lambda c: [
            {"skill": "C++", "avg_salary": 200000, "vacancy_count": 20}
        ])

        client = self._make_client()
        resp = client.get("/analytics/salary-by-stack")
        assert resp.status_code == 200
        assert resp.json()[0]["avg_salary"] == 200000

    def test_500_on_analytics_error(self, monkeypatch):
        import automation.analytics as an
        from automation.analytics import AnalyticsError
        monkeypatch.setattr(an, "top_companies", lambda c, days: (_ for _ in ()).throw(AnalyticsError("boom")))

        client = self._make_client()
        resp = client.get("/analytics/top-companies")
        assert resp.status_code == 500
