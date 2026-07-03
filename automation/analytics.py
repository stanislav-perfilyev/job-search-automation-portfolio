#!/usr/bin/env python3
"""
automation/analytics.py — OLAP аналитика из ClickHouse.

Запуск:
  python analytics.py top-companies [--days 30]
  python analytics.py conversion     [--source hh.kz]
  python analytics.py skill-trends   [--months 3]
  python analytics.py salary-stack

Требует: CLICKHOUSE_URL в .env
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from db.clickhouse_writer import ClickHouseWriter, ClickHouseError

logger = logging.getLogger(__name__)


# ── Кастомные исключения ──────────────────────────────────────────────────

class AnalyticsError(Exception):
    """Ошибка аналитического запроса."""


# ── Query-функции ─────────────────────────────────────────────────────────

def top_companies(client, days: int = 30) -> list[dict]:
    """
    Топ компаний по количеству вакансий за последние N дней.

    Returns list[{company, count}] DESC.
    """
    sql = """
        SELECT
            company,
            count() AS cnt
        FROM analytics.vacancy_events
        WHERE event_date >= today() - {days:UInt32}
        GROUP BY company
        ORDER BY cnt DESC
        LIMIT 20
    """
    try:
        result = client.query(sql, parameters={"days": days})
        return [{"company": row[0], "count": row[1]} for row in result.result_rows]
    except Exception as exc:
        raise AnalyticsError(f"top_companies: {exc}") from exc


def conversion_by_source(client, source: str | None = None) -> list[dict]:
    """
    Конверсия по источникам: applied → interview → offer.

    Returns list[{source, applied, interview, offer, rejected, conv_pct}].
    conv_pct = offer / applied * 100.
    """
    where = "WHERE 1=1"
    params: dict = {}
    if source:
        where += " AND source = {source:String}"
        params["source"] = source

    sql = f"""
        SELECT
            source,
            countIf(action = 'applied')   AS applied,
            countIf(action = 'interview') AS interview,
            countIf(action = 'offer')     AS offer,
            countIf(action = 'rejected')  AS rejected
        FROM analytics.vacancy_events
        {where}
        GROUP BY source
        ORDER BY applied DESC
    """
    try:
        result = client.query(sql, parameters=params)
        rows = []
        for row in result.result_rows:
            src, app, intv, ofr, rej = row
            conv = round(ofr / app * 100, 1) if app > 0 else 0.0
            rows.append({
                "source":    src,
                "applied":   app,
                "interview": intv,
                "offer":     ofr,
                "rejected":  rej,
                "conv_pct":  conv,
            })
        return rows
    except Exception as exc:
        raise AnalyticsError(f"conversion_by_source: {exc}") from exc


def skill_gap_trends(client, months: int = 3) -> list[dict]:
    """
    Топ skill gaps за последние N месяцев, с динамикой «растёт/падает».

    Returns list[{skill, total, prev_month, curr_month, trend}].
    trend: up | down | stable
    """
    sql = """
        SELECT
            skill,
            sum(cnt)                                      AS total,
            sumIf(cnt, month >= toStartOfMonth(today()) - INTERVAL 1 MONTH
                       AND month < toStartOfMonth(today()))    AS prev_month,
            sumIf(cnt, month >= toStartOfMonth(today()))       AS curr_month
        FROM analytics.skill_gap_monthly
        WHERE month >= toStartOfMonth(today()) - toIntervalMonth({months:UInt32})
        GROUP BY skill
        ORDER BY total DESC
        LIMIT 25
    """
    try:
        result = client.query(sql, parameters={"months": months})
        rows = []
        for row in result.result_rows:
            skill, total, prev, curr = row
            if curr > prev:
                trend = "up"
            elif curr < prev:
                trend = "down"
            else:
                trend = "stable"
            rows.append({
                "skill":      skill,
                "total":      total,
                "prev_month": prev,
                "curr_month": curr,
                "trend":      trend,
            })
        return rows
    except Exception as exc:
        raise AnalyticsError(f"skill_gap_trends: {exc}") from exc


def salary_by_stack(client) -> list[dict]:
    """
    Средняя зарплата по ключевым skill gaps.

    Returns list[{skill, avg_salary, vacancy_count}] для вакансий с salary_from > 0.
    """
    sql = """
        SELECT
            skill,
            round(avg(salary_from))     AS avg_salary,
            count()                     AS cnt
        FROM analytics.vacancy_events
        ARRAY JOIN skill_gaps AS skill
        WHERE salary_from IS NOT NULL
          AND salary_from > 0
          AND skill != ''
        GROUP BY skill
        HAVING cnt >= 2
        ORDER BY avg_salary DESC
        LIMIT 20
    """
    try:
        result = client.query(sql)
        return [
            {"skill": row[0], "avg_salary": int(row[1]), "vacancy_count": row[2]}
            for row in result.result_rows
        ]
    except Exception as exc:
        raise AnalyticsError(f"salary_by_stack: {exc}") from exc


# ── CLI ───────────────────────────────────────────────────────────────────

def _get_client():
    """Подключиться к ClickHouse или упасть с понятным сообщением."""
    writer = ClickHouseWriter(graceful=False)
    if writer._client is None:
        print("❌ ClickHouse недоступен. Проверьте CLICKHOUSE_URL в .env")
        sys.exit(1)
    return writer._client


def _print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("(нет данных)")
        return
    keys = list(rows[0].keys())
    widths = {k: max(len(k), max(len(str(r[k])) for r in rows)) for k in keys}
    header = "  ".join(k.ljust(widths[k]) for k in keys)
    sep    = "  ".join("-" * widths[k] for k in keys)
    print(header)
    print(sep)
    for row in rows:
        print("  ".join(str(row[k]).ljust(widths[k]) for k in keys))


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser(description="ClickHouse OLAP аналитика")
    parser.add_argument("command", choices=["top-companies", "conversion", "skill-trends", "salary-stack"])
    parser.add_argument("--days",   type=int, default=30,   help="Дней для top-companies (по умолч. 30)")
    parser.add_argument("--months", type=int, default=3,    help="Месяцев для skill-trends (по умолч. 3)")
    parser.add_argument("--source", default=None,           help="Источник для conversion (по умолч. все)")
    parser.add_argument("--json",   action="store_true",    help="Вывод в JSON")
    args = parser.parse_args()

    client = _get_client()

    try:
        if args.command == "top-companies":
            data = top_companies(client, days=args.days)
            print(f"\n📊 Топ компаний за {args.days} дней:\n")
        elif args.command == "conversion":
            data = conversion_by_source(client, source=args.source)
            print(f"\n📈 Конверсия по источникам:\n")
        elif args.command == "skill-trends":
            data = skill_gap_trends(client, months=args.months)
            print(f"\n📉 Skill gap тренды за {args.months} мес.:\n")
        elif args.command == "salary-stack":
            data = salary_by_stack(client)
            print(f"\n💰 Зарплата по стеку:\n")
        else:
            parser.print_help()
            sys.exit(1)
    except AnalyticsError as exc:
        print(f"❌ {exc}")
        sys.exit(1)

    if args.json:
        _print_json(data)
    else:
        _print_table(data)


if __name__ == "__main__":
    main()
