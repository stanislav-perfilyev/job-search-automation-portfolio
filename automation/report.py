#!/usr/bin/env python3
"""
report.py — отчёт сессии поиска работы из PostgreSQL.

Использование:
  python report.py [--mode full|check] [--days 7]
"""

import os
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path
from collections import Counter

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from db import Database

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID", "")

STALE_DAYS = 7


def build_report(days: int, mode: str) -> str:
    today = date.today()
    since = today - timedelta(days=days)

    with Database() as db:
        # Все вакансии за период
        all_rows  = db.get_vacancies(since=since, limit=1000)
        # За сегодня
        today_rows = [r for r in all_rows if r.get("date") == today]
        # Сводная статистика за период
        stats = db.get_stats(days=days)
        # Зависшие
        summary = db.get_vacancy_summary(stale_days=STALE_DAYS)

    vac = stats["vacancies"]
    fl  = stats["freelance"]

    # Источники за сегодня
    sources_today: Counter = Counter(r.get("source", "?") for r in today_rows)
    # Статусы всего в базе
    status_all: Counter = Counter((r.get("status") or "?").lower() for r in db.get_vacancies(limit=2000) if True)

    # Вернём для режима check
    lines = [
        f"📋 ОТЧЁТ {'СЕССИИ' if mode == 'full' else 'ПРОВЕРКИ'} — {today.strftime('%d.%m.%Y')}",
        f"{'─'*44}",
    ]

    if today_rows:
        lines.append(f"\n📥 Добавлено сегодня: {len(today_rows)} вакансий")
        for src, cnt in sources_today.most_common():
            lines.append(f"   {src}: {cnt}")

    lines += [
        f"\n📊 Статистика за {days} дней:",
        f"   Всего вакансий:    {vac['total_vacancies']}",
        f"   Ожидают ответа:    {vac['applied']}",
        f"   Интервью:          {vac['interviews']}",
        f"   Офферы:            {vac['offers']}",
        f"   Отказы:            {vac['rejected']}",
        f"\n⏰ Зависших (>{STALE_DAYS}д без ответа): {summary['stale']}",
    ]
    if summary.get("stale_list"):
        for s in summary["stale_list"][:5]:
            lines.append(f"   • {s}")
        if len(summary["stale_list"]) > 5:
            lines.append(f"   ...ещё {len(summary['stale_list']) - 5}")

    lines += [
        f"\n💼 Фриланс за {days} дней:",
        f"   Откликов:   {fl['total']}",
        f"   Connects:   {fl['connects_used'] or 0}",
        f"   Контракты:  {fl['contracts']}",
        f"   Интервью:   {fl['interviews']}",
    ]

    if vac["total_vacancies"] > 0:
        conv = round((vac["interviews"] or 0) / vac["total_vacancies"] * 100, 1)
        lines.append(f"\n📈 Конверсия: {conv}% (откликов → интервью)")

    return "\n".join(lines)


def send_tg(text: str) -> None:
    import urllib.request, urllib.parse
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text[:4096]})
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        data=data.encode(), method="POST",
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Отчёт сессии поиска работы")
    parser.add_argument("--mode", choices=["full", "check"], default="check")
    parser.add_argument("--days", type=int, default=7, help="Период статистики в днях")
    parser.add_argument("--tg",   action="store_true", help="Отправить в Telegram")
    args = parser.parse_args()

    try:
        report = build_report(args.days, args.mode)
    except Exception as e:
        print(f"❌ PostgreSQL: {e}", file=sys.stderr)
        sys.exit(1)

    print(report)

    if args.tg:
        try:
            send_tg(report)
            print("\n✅ Отправлено в Telegram")
        except Exception as e:
            print(f"\n⚠️  Telegram: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
