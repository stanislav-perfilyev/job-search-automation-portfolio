#!/usr/bin/env python3
"""
db_stats.py — статистика поиска работы из PostgreSQL за последние N дней.

Использование:
  python db_stats.py            # 7 дней, вывод в терминал
  python db_stats.py --days 30  # последние 30 дней
  python db_stats.py --tg       # + отправить отчёт в Telegram

Данные из таблиц:
  vacancies         — все вакансии (статус, источник, дата)
  freelance_projects — фриланс-отклики
"""

import argparse
import os
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from db import Database

TG_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")


# ── Запросы к БД ──────────────────────────────────────────────────────────

def fetch_vacancy_stats(db: Database, days: int) -> dict:
    since = date.today() - timedelta(days=days)
    rows = db.get_vacancies(since=since, limit=1000)

    by_status  = Counter(r["status"]  for r in rows)
    by_source  = Counter(r["source"]  for r in rows)
    by_company = Counter(r["company"] for r in rows)

    # Все вакансии (без фильтра по дате) для общего счёта
    total_all = db.get_vacancies(limit=5000)
    return {
        "total_period": len(rows),
        "total_all":    len(total_all),
        "since":        since,
        "by_status":    dict(by_status.most_common()),
        "by_source":    dict(by_source.most_common(10)),
        "top_companies": by_company.most_common(5),
    }


def fetch_freelance_stats(db: Database, days: int) -> dict:
    since = date.today() - timedelta(days=days)
    # get_vacancies нет для фриланса — используем get_stats
    stats = db.get_stats(days=days)
    return stats.get("freelance", {})


# ── Форматирование ────────────────────────────────────────────────────────

STATUS_RU = {
    "new":       "🆕 Новых",
    "applied":   "📤 Откликов",
    "interview": "🎯 Интервью",
    "offer":     "🏆 Офферов",
    "rejected":  "❌ Отказов",
    "ignored":   "🚫 Игнорировано",
}

SOURCE_ICON = {
    "hh.kz":      "🟠",
    "Habr":       "🔵",
    "LinkedIn":   "💼",
    "корп. сайт": "🏢",
    "Upwork":     "🟢",
    "FL.ru":      "🟡",
    "Kwork":      "🔴",
}


def format_console(v_stats: dict, fl_stats: dict, days: int) -> str:
    lines = []
    lines.append(f"{'═'*45}")
    lines.append(f"📊 СТАТИСТИКА ЗА {days} ДНЕЙ  ({v_stats['since'].strftime('%d.%m')} – сегодня)")
    lines.append(f"{'═'*45}")

    lines.append(f"\n📁 ВАКАНСИИ")
    lines.append(f"   За период:  {v_stats['total_period']}")
    lines.append(f"   Всего в БД: {v_stats['total_all']}")

    if v_stats["by_status"]:
        lines.append(f"\n   Статусы:")
        for st, cnt in v_stats["by_status"].items():
            label = STATUS_RU.get(st, st)
            lines.append(f"     {label:<18} {cnt}")

    if v_stats["by_source"]:
        lines.append(f"\n   Источники:")
        for src, cnt in v_stats["by_source"].items():
            icon = SOURCE_ICON.get(src, "•")
            lines.append(f"     {icon} {src:<16} {cnt}")

    if v_stats["top_companies"]:
        lines.append(f"\n   Топ-5 компаний:")
        for company, cnt in v_stats["top_companies"]:
            lines.append(f"     • {company[:30]}: {cnt}")

    # Фриланс (из get_stats)
    fl_total     = fl_stats.get("total", 0) or 0
    fl_connects  = fl_stats.get("connects_used", 0) or 0
    fl_contracts = fl_stats.get("contracts", 0) or 0
    fl_interviews= fl_stats.get("interviews", 0) or 0
    if fl_total > 0:
        lines.append(f"\n💻 ФРИЛАНС (за {days} дней)")
        lines.append(f"   Откликов:   {fl_total}")
        lines.append(f"   Connects:   {fl_connects}")
        if fl_interviews: lines.append(f"   Интервью:   {fl_interviews}")
        if fl_contracts:  lines.append(f"   Контрактов: {fl_contracts}")

    lines.append(f"\n{'═'*45}")
    return "\n".join(lines)


def format_telegram(v_stats: dict, fl_stats: dict, days: int) -> str:
    lines = [
        f"📊 <b>Поиск работы — итоги {days} дней</b>",
        f"📅 {v_stats['since'].strftime('%d.%m')} – {date.today().strftime('%d.%m.%Y')}",
        "",
        f"<b>Вакансии за период:</b> {v_stats['total_period']}",
        f"<b>Всего в базе:</b> {v_stats['total_all']}",
    ]

    by_status = v_stats["by_status"]
    if by_status:
        lines.append("")
        lines.append("<b>Статусы:</b>")
        for st, cnt in by_status.items():
            label = STATUS_RU.get(st, st)
            lines.append(f"  {label}: <b>{cnt}</b>")

    by_source = v_stats["by_source"]
    if by_source:
        lines.append("")
        lines.append("<b>Источники:</b>")
        for src, cnt in list(by_source.items())[:5]:
            icon = SOURCE_ICON.get(src, "•")
            lines.append(f"  {icon} {src}: {cnt}")

    top = v_stats["top_companies"]
    if top:
        lines.append("")
        lines.append("<b>Топ компаний:</b>")
        for company, cnt in top:
            lines.append(f"  • {company[:25]}: {cnt}")

    fl_total     = fl_stats.get("total", 0) or 0
    fl_connects  = fl_stats.get("connects_used", 0) or 0
    fl_contracts = fl_stats.get("contracts", 0) or 0
    if fl_total > 0:
        lines.append("")
        lines.append(f"💻 <b>Фриланс за период:</b> {fl_total}")
        lines.append(f"💻 Connects потрачено: {fl_connects}")
        if fl_contracts:
            lines.append(f"💻 Контрактов: {fl_contracts}")

    return "\n".join(lines)


# ── Telegram ──────────────────────────────────────────────────────────────

def send_telegram(text: str):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("⚠️  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы")
        return
    r = requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    if r.ok:
        print("✅ Отправлено в Telegram")
    else:
        print(f"❌ Telegram ошибка: {r.text[:200]}")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Статистика из PostgreSQL")
    parser.add_argument("--days", type=int, default=7,
                        help="Период в днях (по умолч. 7)")
    parser.add_argument("--tg",  action="store_true",
                        help="Отправить отчёт в Telegram")
    args = parser.parse_args()

    print(f"🔌 Подключаюсь к PostgreSQL...")
    try:
        db = Database()
        db.connect()
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        sys.exit(1)

    try:
        print(f"📊 Запрашиваю статистику за {args.days} дней...")
        v_stats  = fetch_vacancy_stats(db, args.days)
        raw_stats = db.get_stats(days=args.days)
        fl_data   = raw_stats.get("freelance", {})
    finally:
        db.close()

    report_console = format_console(v_stats, fl_data, args.days)
    print("\n" + report_console)

    if args.tg:
        tg_text = format_telegram(v_stats, fl_data, args.days)
        send_telegram(tg_text)


if __name__ == "__main__":
    main()
