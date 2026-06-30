#!/usr/bin/env python3
"""
skill_gap_report.py — анализ пробелов скиллов из PostgreSQL.

Читает колонку skill_gaps из таблицы vacancies, агрегирует рейтинг.

Использование:
  python skill_gap_report.py          # вывод в терминал
  python skill_gap_report.py --tg     # + отправить в Telegram
"""

import os
import sys
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from db import Database

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TG_CHAT_ID", "")

REJECTION_STATUSES = {"rejected", "отказ", "отказали"}


def parse_gaps(raw: str) -> list[str]:
    """'Boost, Docker, Qt6.5' → ['Boost', 'Docker', 'Qt6.5']"""
    if not raw:
        return []
    parts = re.split(r"[;,\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def analyze(rows: list[dict]) -> dict:
    counter: Counter = Counter()
    rejection_counter: Counter = Counter()
    by_source: defaultdict = defaultdict(Counter)

    for row in rows:
        skills = parse_gaps(row.get("skill_gaps") or "")
        is_rejection = (row.get("status", "") or "").lower() in REJECTION_STATUSES
        source = row.get("source", "неизвестно")
        for skill in skills:
            counter[skill] += 1
            if is_rejection:
                rejection_counter[skill] += 1
            by_source[source][skill] += 1

    return {
        "total_vacancies": len(rows),
        "vacancies_with_gaps": sum(1 for r in rows if r.get("skill_gaps")),
        "counter": counter,
        "rejection_counter": rejection_counter,
        "by_source": by_source,
    }


def format_report(data: dict) -> str:
    lines = [
        "📊 SKILL GAP — анализ пробелов навыков (из PostgreSQL)",
        f"Вакансий всего: {data['total_vacancies']} | С пробелами: {data['vacancies_with_gaps']}",
        "",
        "🔴 ТОП-15 пробелов (по частоте):",
    ]
    for skill, cnt in data["counter"].most_common(15):
        rej = data["rejection_counter"].get(skill, 0)
        bar = "▓" * min(cnt, 10)
        rej_mark = f" (отказов: {rej})" if rej else ""
        lines.append(f"  {bar} {cnt}× — {skill}{rej_mark}")

    if data["rejection_counter"]:
        lines += ["", "⚠️  Коррелируют с отказами:"]
        for skill, cnt in data["rejection_counter"].most_common(5):
            lines.append(f"  {cnt}× — {skill}")

    return "\n".join(lines)


def send_tg(text: str) -> None:
    import urllib.request, urllib.parse
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    payload = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        data=payload.encode(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def main() -> None:
    send_to_tg = "--tg" in sys.argv

    try:
        with Database() as db:
            rows = db.get_skill_gaps(limit=500)
    except Exception as e:
        print(f"❌ Нет подключения к PostgreSQL: {e}", file=sys.stderr)
        sys.exit(1)

    if not rows:
        print("Нет данных о пробелах скиллов в БД.")
        print("Добавьте --gap при вводе вакансии: python add_vacancy.py --gap 'Boost, Docker'")
        sys.exit(0)

    data = analyze(rows)
    report = format_report(data)
    print(report)

    if send_to_tg:
        try:
            send_tg(report[:4096])
            print("\n✅ Отправлено в Telegram")
        except Exception as e:
            print(f"\n⚠️  Telegram: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
