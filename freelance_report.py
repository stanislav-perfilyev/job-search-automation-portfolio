#!/usr/bin/env python3
"""
freelance_report.py — отчёт по фриланс-откликам из PostgreSQL.

Использование:
  python freelance_report.py [--days 30] [--tg]
"""

import os
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path
from collections import Counter, defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from db import Database

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID", "")


def build_report(days: int) -> str:
    since = date.today() - timedelta(days=days)

    with Database() as db:
        rows = db.get_freelance(since=since, limit=500)
        stats = db.get_stats(days=days)

    if not rows:
        return f"📭 Нет фриланс-откликов за {days} дней."

    fl = stats["freelance"]

    # Агрегация
    by_platform: Counter = Counter(r.get("platform", "?") for r in rows)
    by_status:   Counter = Counter((r.get("status") or "sent").lower() for r in rows)

    total_budget  = sum(float(r["budget"] or 0)        for r in rows if r.get("budget"))
    total_rate    = sum(float(r["our_rate"] or 0)      for r in rows if r.get("our_rate"))
    total_connect = sum(int(r["connects_spent"] or 0)  for r in rows)
    contracts     = [r for r in rows if (r.get("status") or "").lower() == "contract"]

    # Конверсия
    conv = f"{len(contracts)/len(rows)*100:.1f}%" if rows else "0%"

    lines = [
        f"💼 ФРИЛАНС-ОТЧЁТ — последние {days} дней",
        f"{'─'*40}",
        f"Откликов:    {len(rows)}",
        f"Connects:    {total_connect}",
        f"Контракты:   {len(contracts)} ({conv} конверсия)",
        "",
        "По платформам:",
    ]
    for plat, cnt in by_platform.most_common():
        lines.append(f"   {plat}: {cnt}")

    lines.append("\nПо статусам:")
    for st, cnt in by_status.most_common():
        lines.append(f"   {st}: {cnt}")

    if total_budget > 0:
        lines.append(f"\nСумма заявленных бюджетов: ${total_budget:,.0f}")
    if total_rate > 0:
        lines.append(f"Наша общая ставка:          ${total_rate:,.0f}")

    if contracts:
        lines.append("\n🏆 Контракты:")
        for c in contracts[-5:]:
            lines.append(f"   {c.get('project_title','')} | {c.get('client','')} | ${c.get('budget') or '?'}")

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
    parser = argparse.ArgumentParser(description="Отчёт по фрилансу")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--tg",   action="store_true")
    args = parser.parse_args()

    try:
        report = build_report(args.days)
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
