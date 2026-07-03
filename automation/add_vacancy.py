#!/usr/bin/env python3
"""
add_vacancy.py — добавляет вакансию в PostgreSQL (таблица vacancies).

Использование:
  python add_vacancy.py --vacancy "C++ разработчик" --company "Компания" \
    --url "https://example.com" --source "hh.kz" --template "шаблон С" \
    --date "13.06.2026"

Источники: hh.kz | корп. сайт | LinkedIn | hh.ru
Шаблоны:   шаблон А | шаблон В | шаблон С
Дата:      формат DD.MM.YYYY (по умолчанию — сегодня)

Резервная Sheets-версия: add_vacancy_sheets.py
Лог операций: db.log
"""

import argparse
import logging
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from db import Database
from db.clickhouse_writer import ClickHouseWriter

# ── Логирование в db.log ──────────────────────────────────────────────────
LOG_FILE = Path(__file__).resolve().parents[1] / "db.log"
try:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
    )
except PermissionError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )
    print("[WARN] db.log заблокирован другим процессом, лог пишется в консоль")
log = logging.getLogger(__name__)

# ── Маппинг статусов ──────────────────────────────────────────────────────
STATUS_MAP = {
    "ожидание":  "applied",
    "отклик":    "applied",
    "applied":   "applied",
    "интервью":  "interview",
    "interview": "interview",
    "оффер":     "offer",
    "offer":     "offer",
    "отказ":     "rejected",
    "rejected":  "rejected",
    "ignored":   "ignored",
    "new":       "new",
}


def _parse_date(s: str) -> date:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Неизвестный формат даты: {s!r}")


def main():
    parser = argparse.ArgumentParser(description="Добавить вакансию в PostgreSQL")
    parser.add_argument("--vacancy",  required=True,  help="Название вакансии")
    parser.add_argument("--company",  required=True,  help="Компания")
    parser.add_argument("--url",      required=True,  help="Ссылка на вакансию")
    parser.add_argument("--source",   required=True,
                        help="Источник: hh.kz | корп. сайт | LinkedIn | hh.ru")
    parser.add_argument("--template", default="С",
                        help="Шаблон: А | В | С (или 'шаблон С') — по умолч. С")
    parser.add_argument("--date",
                        default=datetime.today().strftime("%d.%m.%Y"),
                        help="Дата отклика DD.MM.YYYY")
    parser.add_argument("--status",   default="ожидание",
                        help="Статус (по умолч. ожидание)")
    parser.add_argument("--comment",  default="", help="Комментарий")
    parser.add_argument("--hr",       default="", help="Контакт HR (в notes)")
    parser.add_argument("--gap",      default="", help="Пробелы скиллов через запятую: 'Boost, Docker'")
    args = parser.parse_args()

    # Дата
    try:
        d = _parse_date(args.date)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Нормализация статуса
    status = STATUS_MAP.get(args.status.lower().strip(), "applied")

    # Нормализация шаблона: "шаблон С" → "С"
    template = args.template.strip()
    if template.lower().startswith("шаблон"):
        template = template.split()[-1]

    # Notes: комментарий + HR если заданы
    notes_parts = [p for p in (args.comment, args.hr) if p]
    notes = " | ".join(notes_parts) or None

    vacancy = {
        "date":          d,
        "title":         args.vacancy,
        "company":       args.company,
        "url":           args.url,
        "source":        args.source,
        "status":        status,
        "template_used": template or None,
        "skill_gaps":    args.gap.strip() or None,
        "notes":         notes,
    }

    print(f"💾 Записываю в PostgreSQL...")
    try:
        with Database() as db:
            vacancy_id = db.add_vacancy(vacancy)
            try:
                db.log_event("vacancy_added", 1.0, {
                    "source": args.source, "status": status, "vacancy_id": vacancy_id
                })
            except Exception:
                pass  # не прерывать основной поток из-за KPI

        # ── ClickHouse: параллельная OLAP-запись (graceful skip) ──────────
        skill_list = [s.strip() for s in args.gap.split(",") if s.strip()] if args.gap else []
        ch = ClickHouseWriter()  # graceful=True по умолчанию
        ch.log_vacancy_event(
            vacancy_id=vacancy_id,
            action=status,
            source=args.source,
            company=args.company,
            skill_gaps=skill_list,
            event_date=d,
        )
        if skill_list:
            ch.log_skill_gaps(skill_list, event_date=d)
        ch.close()

        msg = (f"add_vacancy | id={vacancy_id} | {args.vacancy} | "
               f"{args.company} | {args.source} | {d} | {status}")
        log.info(msg)
        print(f"✅ Вакансия добавлена (id={vacancy_id})")
        print(f"   {args.vacancy} | {args.company} | {args.source} | {args.date} | {status}")
    except Exception as e:
        log.error(f"add_vacancy ERROR: {e} | {args.vacancy} | {args.company} | {args.url}")
        print(f"❌ Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
