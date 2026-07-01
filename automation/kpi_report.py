#!/usr/bin/env python3
"""
kpi_report.py — еженедельный KPI-отчёт из PostgreSQL.

Использование:
  python kpi_report.py [--days 7] [--tg]
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


def build_kpi(days: int) -> str:
    since = date.today() - timedelta(days=days)

    with Database() as db:
        stats   = db.get_stats(days=days)
        vacrows = db.get_vacancies(since=since, limit=500)
        flrows  = db.get_freelance(since=since, limit=500)
        summary = db.get_vacancy_summary(stale_days=7)

    vac = stats["vacancies"]
    fl  = stats["freelance"]

    # Дополнительные расчёты
    by_source = Counter(r.get("source", "?") for r in vacrows)
    total_new  = len(vacrows)
    applied    = vac.get("applied", 0)
    interviews = vac.get("interviews", 0)
    offers     = vac.get("offers", 0)
    rejected   = vac.get("rejected", 0)

    conv_i = f"{interviews/max(total_new,1)*100:.1f}%"
    conv_o = f"{offers/max(interviews,1)*100:.1f}%" if interviews else "—"

    fl_total    = fl.get("total", 0) or 0
    fl_connects = int(fl.get("connects_used") or 0)
    fl_contract = fl.get("contracts", 0) or 0

    lines = [
        f"📊 KPI ОТЧЁТ — {date.today().strftime('%d.%m.%Y')} (за {days} дней)",
        f"{'═'*44}",
        "",
        "🔍 ПОИСК РАБОТЫ",
        f"  Новых вакансий найдено:  {total_new}",
        f"  В ожидании ответа:       {summary['waiting']}",
        f"  Зависших (>7д):          {summary['stale']}",
        f"  Интервью:                {interviews}",
        f"  Офферы:                  {offers}",
        f"  Отказы:                  {rejected}",
        f"  Конверсия отклик→интервью: {conv_i}",
        f"  Конверсия интервью→оффер:  {conv_o}",
        "",
        "  По источникам:",
    ]
    for src, cnt in by_source.most_common(5):
        lines.append(f"    {src}: {cnt}")

    if summary.get("stale_list"):
        lines += ["", "  ⏰ Зависшие:"]
        for s in summary["stale_list"][:3]:
            lines.append(f"    • {s}")

    lines += [
        "",
        "💼 ФРИЛАНС",
        f"  Откликов:   {fl_total}",
        f"  Connects:   {fl_connects}",
        f"  Контракты:  {fl_contract}",
    ]

    # Итог
    total_activity = total_new + fl_total
    lines += [
        "",
        f"{'─'*44}",
        f"🚀 Общая активность: {total_activity} действий за {days} дней",
        f"   ({total_new} вакансий + {fl_total} фриланс)",
    ]

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
    parser = argparse.ArgumentParser(description="Еженедельный KPI отчёт")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--tg",   action="store_true")
    args = parser.parse_args()

    try:
        report = build_kpi(args.days)
    except Exception as e:
        print(f"❌ PostgreSQL: {e}", file=sys.stderr)
        sys.exit(1)

    print(report)

    if args.tg:
        try:
            send_tg(report)
            print("\n✅ Telegram")
        except Exception as e:
            print(f"\n⚠️  Telegram: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
