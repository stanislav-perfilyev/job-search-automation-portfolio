#!/usr/bin/env python3
"""
follow_up.py — проверяет вакансии без ответа за N дней из PostgreSQL.

Использование:
  python follow_up.py [--days 7] [--tg]
"""

import os
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from db import Database

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID", "")

WAITING_STATUSES = {"applied", "ожидание", ""}


def find_stale(days: int) -> list[dict]:
    """Вакансии с ожиданием дольше days без смены статуса."""
    cutoff = date.today() - timedelta(days=days)
    with Database() as db:
        rows = db.get_vacancies(limit=1000)
    stale = []
    for r in rows:
        if (r.get("status") or "").lower().strip() not in WAITING_STATUSES:
            continue
        v_date = r.get("date")
        if not v_date:
            continue
        if isinstance(v_date, str):
            from datetime import datetime
            try:
                v_date = datetime.strptime(v_date, "%Y-%m-%d").date()
            except ValueError:
                continue
        if v_date <= cutoff:
            age = (date.today() - v_date).days
            stale.append({
                "vacancy": r.get("title", ""),
                "company": r.get("company", ""),
                "source":  r.get("source", ""),
                "url":     r.get("url", ""),
                "age":     age,
                "date":    v_date.strftime("%d.%m.%Y"),
            })
    stale.sort(key=lambda x: -x["age"])
    return stale


def format_report(stale: list[dict], days: int) -> str:
    if not stale:
        return f"✅ Нет вакансий без ответа дольше {days} дней."
    lines = [f"⏰ Follow-up — вакансии без ответа > {days} дней ({len(stale)} шт.):", ""]
    for i, v in enumerate(stale, 1):
        lines.append(f"{i}. {v['vacancy']} / {v['company']} ({v['source']})")
        lines.append(f"   Ждём: {v['age']} дней | отклик: {v['date']}")
        if v["url"]:
            lines.append(f"   {v['url']}")
        lines.append("")
    return "\n".join(lines).strip()


def send_tg(text: str) -> None:
    import urllib.request, urllib.parse
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("TG_BOT_TOKEN / TG_CHAT_ID не заданы — Telegram пропущен")
        return
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text[:4096]})
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        data=data.encode(), method="POST",
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Follow-up по просроченным вакансиям")
    parser.add_argument("--days", type=int, default=7, help="Порог дней без ответа (по умолч. 7)")
    parser.add_argument("--tg",   action="store_true", help="Отправить в Telegram")
    args = parser.parse_args()

    try:
        stale = find_stale(args.days)
    except Exception as e:
        print(f"❌ PostgreSQL: {e}", file=sys.stderr)
        sys.exit(1)

    report = format_report(stale, args.days)
    print(report)

    if args.tg:
        try:
            send_tg(report)
            print("\n✅ Отправлено в Telegram")
        except Exception as e:
            print(f"\n⚠️  Telegram: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
