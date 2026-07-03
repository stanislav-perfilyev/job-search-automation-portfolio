#!/usr/bin/env python3
"""
db/clickhouse_writer.py — ClickHouse аналитическое хранилище.

Параллельная запись: PostgreSQL (OLTP) + ClickHouse (OLAP).
Graceful skip: при недоступности CH основной поток не прерывается.

Таблицы:
  analytics.vacancy_events  — событие на вакансию (applied, interview, offer, ...)
  analytics.skill_gap_monthly — skill gap тренды по месяцам

Использование::

    writer = ClickHouseWriter()
    writer.log_vacancy_event(
        vacancy_id=42,
        action="applied",
        source="hh.kz",
        company="Yandex",
    )
    writer.log_skill_gaps(["Qt", "eBPF"])
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Кастомные исключения
class ClickHouseError(Exception):
    """Базовое исключение ClickHouse."""


class ClickHouseConfigError(ClickHouseError):
    """CLICKHOUSE_URL не задан или некорректен."""


class ClickHouseConnectionError(ClickHouseError):
    """Нет соединения с ClickHouse."""


class ClickHouseWriter:
    """
    Тонкая обёртка над clickhouse-connect для записи аналитических событий.

    Все публичные методы подавляют исключения по умолчанию (graceful=True),
    чтобы недоступность ClickHouse не прерывала основной поток записи в PG.
    """

    def __init__(
        self,
        url: Optional[str] = None,
        *,
        graceful: bool = True,
    ) -> None:
        """
        Parameters
        ----------
        url      : clickhouse://user:pass@host:port/database
                   По умолчанию читается из CLICKHOUSE_URL.
        graceful : True → ошибки логируются, но не поднимаются.
        """
        self._graceful = graceful
        self._client = None

        raw_url = url or os.environ.get("CLICKHOUSE_URL", "")
        if not raw_url:
            msg = "CLICKHOUSE_URL не задан"
            if not graceful:
                raise ClickHouseConfigError(msg)
            logger.warning("ClickHouseWriter: %s — аналитика отключена", msg)
            return

        try:
            self._client = self._connect(raw_url)
            logger.info("ClickHouseWriter: подключён к %s", self._safe_url(raw_url))
        except Exception as exc:
            if not graceful:
                raise ClickHouseConnectionError(str(exc)) from exc
            logger.warning("ClickHouseWriter: не удалось подключиться — %s", exc)

    # ── Публичный API ─────────────────────────────────────────────────────

    def log_vacancy_event(
        self,
        *,
        vacancy_id: int,
        action: str,
        source: str,
        company: str,
        salary_from: Optional[int] = None,
        skill_gaps: Optional[list[str]] = None,
        event_date: Optional[date] = None,
    ) -> bool:
        """
        Записать событие по вакансии в analytics.vacancy_events.

        Returns True при успехе, False при ошибке.
        """
        if self._client is None:
            return False

        now = datetime.utcnow()
        row = {
            "event_date":  event_date or now.date(),
            "event_time":  now,
            "vacancy_id":  vacancy_id,
            "action":      action[:64],
            "source":      source[:64],
            "company":     company[:256],
            "salary_from": salary_from,
            "skill_gaps":  skill_gaps or [],
        }
        return self._insert("analytics.vacancy_events", [row])

    def log_skill_gaps(
        self,
        skills: list[str],
        *,
        event_date: Optional[date] = None,
    ) -> bool:
        """
        Записать skill gap тренды в analytics.skill_gap_monthly.

        Гранулярность — месяц (для SummingMergeTree агрегации).
        """
        if self._client is None or not skills:
            return False

        month = (event_date or date.today()).replace(day=1)
        rows = [{"month": month, "skill": s[:128], "cnt": 1} for s in skills]
        return self._insert("analytics.skill_gap_monthly", rows)

    def health_check(self) -> str:
        """Пустая строка = OK; описание = что сломано."""
        if self._client is None:
            return "ClickHouse не подключён (CLICKHOUSE_URL отсутствует или недоступен)"
        try:
            result = self._client.query("SELECT 1")
            if result.result_rows == [(1,)]:
                return ""
            return "ClickHouse вернул неожиданный ответ на SELECT 1"
        except Exception as exc:
            return f"ClickHouse недоступен: {exc}"

    def close(self) -> None:
        """Закрыть соединение."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def __enter__(self) -> "ClickHouseWriter":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Приватные методы ──────────────────────────────────────────────────

    @staticmethod
    def _connect(url: str):
        """Создать clickhouse_connect клиент из URL."""
        try:
            import clickhouse_connect  # noqa: PLC0415
        except ImportError as exc:
            raise ClickHouseError(
                "clickhouse-connect не установлен: pip install clickhouse-connect"
            ) from exc

        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8123
        user = parsed.username or "default"
        password = parsed.password or ""
        database = (parsed.path or "/analytics").lstrip("/") or "analytics"

        return clickhouse_connect.get_client(
            host=host,
            port=port,
            username=user,
            password=password,
            database=database,
            connect_timeout=5,
            send_receive_timeout=30,
        )

    def _insert(self, table: str, rows: list[dict]) -> bool:
        """Вставить строки в таблицу. Returns True при успехе."""
        try:
            import clickhouse_connect  # noqa: PLC0415 (уже импортирован в _connect)
            self._client.insert(table, rows, column_names=list(rows[0].keys()))
            return True
        except Exception as exc:
            if not self._graceful:
                raise
            logger.warning("ClickHouseWriter._insert(%s): %s", table, exc)
            return False

    @staticmethod
    def _safe_url(url: str) -> str:
        """Скрыть пароль в URL для логов."""
        parsed = urlparse(url)
        return parsed._replace(netloc=f"{parsed.hostname}:{parsed.port}").geturl()
