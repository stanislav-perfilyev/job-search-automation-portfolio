#!/usr/bin/env python3
"""
db.py — Database класс для работы с PostgreSQL в job-search проекте.

Использование:
  from db import Database

  db = Database()               # читает DATABASE_URL из env
  db.add_vacancy({...})
  db.add_freelance({...})
  stats = db.get_stats()

Исключения:
  ConfigError       — DATABASE_URL не задан
  DbConnectionError — нет соединения с PostgreSQL
  DbQueryError      — ошибка SQL-запроса
"""

import logging
import os
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Generator

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from exceptions import ConfigError, DbConnectionError, DbQueryError

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "")


class Database:
    """
    Тонкая обёртка над psycopg2 для job-search проекта.

    Все методы принимают dict с данными и возвращают id вставленной записи.
    При конфликте по url — UPDATE (upsert).

    Паттерн использования::

        with Database() as db:
            db.add_vacancy({...})   # коммит при выходе из with

    Или напрямую::

        db = Database()
        try:
            db.connect()
            db.add_vacancy({...})
            db.close()
        except DbConnectionError:
            ...
    """

    def __init__(self, dsn: str = "") -> None:
        self._dsn = dsn or DATABASE_URL
        if not self._dsn:
            raise ConfigError(
                "DATABASE_URL не задан. Добавь в .env или передай dsn= явно."
            )
        self._conn: psycopg2.extensions.connection | None = None

    # ── Соединение ────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Открывает соединение с БД. Идемпотентен — повторный вызов безопасен."""
        if self._conn is not None and not self._conn.closed:
            return
        try:
            self._conn = psycopg2.connect(self._dsn)
            self._conn.autocommit = False
            logger.debug("DB connection established")
        except psycopg2.OperationalError as exc:
            raise DbConnectionError(f"Не удалось подключиться к PostgreSQL: {exc}") from exc

    def close(self) -> None:
        """Закрывает соединение."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.debug("DB connection closed")

    def health_check(self) -> str:
        """
        Проверяет доступность БД.

        Returns:
            Пустая строка — всё в порядке.
            Строка с описанием ошибки — проблема.
        """
        try:
            self.connect()
            with self._conn.cursor() as cur:
                cur.execute("SELECT 1")
            return ""
        except DbConnectionError as exc:
            return f"DB connection failed: {exc}"
        except Exception as exc:  # noqa: BLE001
            return f"DB ping failed: {exc}"

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type:
            if self._conn:
                self._conn.rollback()
                logger.warning("Transaction rolled back due to %s", exc_type.__name__)
        else:
            if self._conn:
                self._conn.commit()
        self.close()

    @contextmanager
    def _cursor(self) -> Generator[psycopg2.extensions.cursor, None, None]:
        self.connect()
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            try:
                yield cur
                self._conn.commit()
            except psycopg2.Error as exc:
                self._conn.rollback()
                raise DbQueryError(str(exc)) from exc
            except Exception:
                self._conn.rollback()
                raise

    # ── Вакансии ──────────────────────────────────────────────────────────────

    def add_vacancy(self, v: dict[str, Any]) -> int:
        """
        Вставляет вакансию. При конфликте url — обновляет статус и notes.

        Обязательные ключи: date, title, company, url, source
        Опциональные: salary_min, salary_max, currency, status,
                      template_used, skill_gaps, notes

        Raises:
            DbQueryError: ошибка SQL
        """
        sql = """
            INSERT INTO vacancies
                (date, title, company, url, salary_min, salary_max, currency,
                 source, status, template_used, skill_gaps, notes)
            VALUES
                (%(date)s, %(title)s, %(company)s, %(url)s,
                 %(salary_min)s, %(salary_max)s, %(currency)s,
                 %(source)s, %(status)s, %(template_used)s,
                 %(skill_gaps)s, %(notes)s)
            ON CONFLICT (url) DO UPDATE SET
                status        = EXCLUDED.status,
                skill_gaps    = COALESCE(EXCLUDED.skill_gaps, vacancies.skill_gaps),
                notes         = COALESCE(EXCLUDED.notes, vacancies.notes)
            RETURNING id
        """
        params = {
            "date":          v.get("date") or date.today(),
            "title":         v["title"],
            "company":       v["company"],
            "url":           v["url"],
            "salary_min":    v.get("salary_min"),
            "salary_max":    v.get("salary_max"),
            "currency":      v.get("currency", "KZT"),
            "source":        v["source"],
            "status":        v.get("status", "applied"),
            "template_used": v.get("template_used") or v.get("template"),
            "skill_gaps":    v.get("skill_gaps"),
            "notes":         v.get("notes") or v.get("comment"),
        }
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.fetchone()["id"]
            logger.debug("Vacancy upserted: id=%s url=%s", row_id, v.get("url", "")[:60])
            return row_id

    def get_vacancies(
        self,
        status: str | None = None,
        source: str | None = None,
        since: date | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Возвращает список вакансий с фильтрами."""
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit}

        if status:
            conditions.append("status = %(status)s")
            params["status"] = status
        if source:
            conditions.append("source = %(source)s")
            params["source"] = source
        if since:
            conditions.append("date >= %(since)s")
            params["since"] = since

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT * FROM vacancies
            {where}
            ORDER BY date DESC, id DESC
            LIMIT %(limit)s
        """
        with self._cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    # ── Фриланс ───────────────────────────────────────────────────────────────

    def add_freelance(self, p: dict[str, Any]) -> int:
        """
        Вставляет фриланс-проект. При конфликте url — обновляет статус.

        Обязательные: date, platform, project_title
        Опциональные: client, url, budget, our_rate, connects_spent,
                      template_used, comment, status

        Raises:
            DbQueryError: ошибка SQL
        """
        sql = """
            INSERT INTO freelance_projects
                (date, platform, project_title, client, url,
                 budget, our_rate, connects_spent,
                 template_used, comment, status)
            VALUES
                (%(date)s, %(platform)s, %(project_title)s, %(client)s, %(url)s,
                 %(budget)s, %(our_rate)s, %(connects_spent)s,
                 %(template_used)s, %(comment)s, %(status)s)
            ON CONFLICT (url) DO UPDATE SET
                status  = EXCLUDED.status,
                comment = COALESCE(EXCLUDED.comment, freelance_projects.comment)
            RETURNING id
        """
        params = {
            "date":           p.get("date") or date.today(),
            "platform":       p["platform"],
            "project_title":  p["project_title"],
            "client":         p.get("client"),
            "url":            p.get("url"),
            "budget":         p.get("budget"),
            "our_rate":       p.get("our_rate"),
            "connects_spent": p.get("connects_spent", 0),
            "template_used":  p.get("template_used"),
            "comment":        p.get("comment"),
            "status":         p.get("status", "sent"),
        }
        with self._cursor() as cur:
            cur.execute(sql, params)
            row_id: int = cur.fetchone()["id"]
            logger.debug("Freelance project upserted: id=%s", row_id)
            return row_id

    # ── Статистика ────────────────────────────────────────────────────────────

    def get_stats(self, days: int = 30) -> dict[str, Any]:
        """Сводная статистика за последние N дней."""
        sql = """
            SELECT
                COUNT(*)                                        AS total_vacancies,
                COUNT(*) FILTER (WHERE status = 'applied')     AS applied,
                COUNT(*) FILTER (WHERE status = 'interview')   AS interviews,
                COUNT(*) FILTER (WHERE status = 'offer')       AS offers,
                COUNT(*) FILTER (WHERE status = 'rejected')    AS rejected,
                COUNT(DISTINCT source)                         AS sources_count
            FROM vacancies
            WHERE date >= CURRENT_DATE - %(days)s
        """
        with self._cursor() as cur:
            cur.execute(sql, {"days": days})
            vac = dict(cur.fetchone())

            cur.execute("""
                SELECT
                    COUNT(*)                                        AS total,
                    SUM(connects_spent)                            AS connects_used,
                    COUNT(*) FILTER (WHERE status = 'contract')   AS contracts,
                    COUNT(*) FILTER (WHERE status = 'interview')  AS interviews
                FROM freelance_projects
                WHERE date >= CURRENT_DATE - %(days)s
            """, {"days": days})
            fl = dict(cur.fetchone())

        return {
            "period_days":     days,
            "vacancies":       vac,
            "freelance":       fl,
            "generated_at":    datetime.now().isoformat(timespec="seconds"),
        }

    def upsert_daily_stats(self, s: dict[str, Any]) -> None:
        """Обновляет или создаёт запись ежедневной статистики."""
        sql = """
            INSERT INTO daily_stats
                (date, vacancies_found, applied_count, freelance_sent,
                 responses_received, interviews, notes)
            VALUES
                (%(date)s, %(vacancies_found)s, %(applied_count)s,
                 %(freelance_sent)s, %(responses_received)s,
                 %(interviews)s, %(notes)s)
            ON CONFLICT (date) DO UPDATE SET
                vacancies_found    = EXCLUDED.vacancies_found,
                applied_count      = EXCLUDED.applied_count,
                freelance_sent     = EXCLUDED.freelance_sent,
                responses_received = EXCLUDED.responses_received,
                interviews         = EXCLUDED.interviews,
                notes              = COALESCE(EXCLUDED.notes, daily_stats.notes)
        """
        params = {
            "date":               s.get("date") or date.today(),
            "vacancies_found":    s.get("vacancies_found", 0),
            "applied_count":      s.get("applied_count", 0),
            "freelance_sent":     s.get("freelance_sent", 0),
            "responses_received": s.get("responses_received", 0),
            "interviews":         s.get("interviews", 0),
            "notes":              s.get("notes"),
        }
        with self._cursor() as cur:
            cur.execute(sql, params)

    # ── Фриланс (чтение) ──────────────────────────────────────────────────────

    def get_freelance(
        self,
        status: str | None = None,
        since: date | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Возвращает список фриланс-проектов с фильтрами."""
        conditions: list[str] = []
        params: dict[str, Any] = {"limit": limit}
        if status:
            conditions.append("status = %(status)s")
            params["status"] = status
        if since:
            conditions.append("date >= %(since)s")
            params["since"] = since
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT * FROM freelance_projects
            {where}
            ORDER BY date DESC, id DESC
            LIMIT %(limit)s
        """
        with self._cursor() as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    # ── Дашборд-статистика ────────────────────────────────────────────────────

    def get_vacancy_summary(self, stale_days: int = 7) -> dict[str, Any]:
        """
        Быстрый дашборд-снимок для morning_brief и Sheets.

        Returns:
            dict: total, waiting, stale, interview, offer, rejected, stale_list.
        """
        with self._cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*)                                                    AS total,
                    COUNT(*) FILTER (WHERE status IN ('applied','ожидание'))   AS waiting,
                    COUNT(*) FILTER (WHERE status = 'interview')               AS interview,
                    COUNT(*) FILTER (WHERE status = 'offer')                   AS offer,
                    COUNT(*) FILTER (WHERE status = 'rejected')                AS rejected
                FROM vacancies
            """)
            row = dict(cur.fetchone())

            cur.execute("""
                SELECT title, company, date
                FROM vacancies
                WHERE status IN ('applied','ожидание')
                  AND date <= CURRENT_DATE - %(days)s
                ORDER BY date ASC
                LIMIT 20
            """, {"days": stale_days})
            stale_rows = cur.fetchall()

        row["stale"] = len(stale_rows)
        row["stale_list"] = [
            f"{r['title']} / {r['company']} ({(date.today() - r['date']).days}д)"
            for r in stale_rows
        ]
        return row

    def url_exists(self, url: str) -> bool:
        """True если URL вакансии уже есть в БД."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT 1 FROM vacancies WHERE url = %(url)s LIMIT 1",
                {"url": url},
            )
            return cur.fetchone() is not None

    def get_urls(self) -> set[str]:
        """Возвращает множество всех URL вакансий (для batch-дедупликации)."""
        with self._cursor() as cur:
            cur.execute("SELECT url FROM vacancies")
            return {r["url"] for r in cur.fetchall()}

    def get_daily_stats_rows(self, days: int = 30) -> list[dict]:
        """Возвращает строки daily_stats за последние N дней."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT * FROM daily_stats
                WHERE date >= CURRENT_DATE - %(days)s
                ORDER BY date DESC
            """, {"days": days})
            return [dict(r) for r in cur.fetchall()]

    def get_skill_gaps(self, limit: int = 500) -> list[dict]:
        """Вакансии с заполненным полем skill_gaps для анализа пробелов."""
        with self._cursor() as cur:
            cur.execute("""
                SELECT date, title, company, source, status, skill_gaps
                FROM vacancies
                WHERE skill_gaps IS NOT NULL AND skill_gaps != ''
                ORDER BY date DESC
                LIMIT %(limit)s
            """, {"limit": limit})
            return [dict(r) for r in cur.fetchall()]
