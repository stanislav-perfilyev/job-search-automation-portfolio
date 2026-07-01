#!/usr/bin/env python3
"""
freelance_add.py — пакетное добавление откликов на фриланс-проекты в PostgreSQL.

Использование:
  python freelance_add.py freelance_session.json

Формат JSON (без изменений):
  {
    "date": "22.06.2026",
    "projects": [
      {
        "project":   "Разработка парсера на C++",
        "client":    "client_nick",
        "url":       "https://www.upwork.com/jobs/...",
        "platform":  "Upwork",        # Upwork | FL.ru | Kwork
        "template":  "A",             # A | B | C | D
        "budget":    "200",           # бюджет клиента (число или строка "$200")
        "our_rate":  "160",           # наша ставка
        "connects":  6,               # Upwork Connects (0 для FL.ru/Kwork)
        "comment":   ""               # опционально
      }
    ]
  }

Лог операций: db.log
"""

import json
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from db import Database

# ── Логирование ───────────────────────────────────────────────────────────
LOG_FILE = Path(__file__).parent / "db.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
)
log = logging.getLogger(__name__)

# ── Маппинг статусов ──────────────────────────────────────────────────────
STATUS_MAP = {
    "отправлен": "sent",
    "sent":      "sent",
    "просмотрен":"viewed",
    "viewed":    "viewed",
    "интервью":  "interview",
    "interview": "interview",
    "в работе":  "contract",
    "contract":  "contract",
    "завершён":  "closed",
    "closed":    "closed",
    "отказ":     "rejected",
    "rejected":  "rejected",
}


def _parse_money(s) -> float | None:
    """Парсит строку вроде '15000 ₽', '$200', '160' → float или None."""
    if s is None or str(s).strip() == "":
        return None
    digits = re.sub(r"[^\d.,]", "", str(s)).replace(",", ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def _parse_date(s: str) -> date:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return date.today()


def _build_record(p: dict, d: date) -> dict:
    """Строит dict для db.add_freelance из JSON-проекта."""
    template = p.get("template", "").strip()
    if template.lower().startswith("шаблон"):
        template = template.split()[-1]

    platform = p.get("platform", "Upwork")
    connects = int(p.get("connects", 0))

    raw_status = p.get("status", "Отправлен")
    status = STATUS_MAP.get(raw_status.lower().strip(), "sent")

    url = p.get("url", "").strip() or None

    return {
        "date":           d,
        "platform":       platform,
        "project_title":  p["project"],
        "client":         p.get("client") or None,
        "url":            url,
        "budget":         _parse_money(p.get("budget")),
        "our_rate":       _parse_money(p.get("our_rate")),
        "connects_spent": connects,
        "template_used":  template or None,
        "comment":        p.get("comment") or None,
        "status":         status,
    }


def main():
    if len(sys.argv) < 2:
        print("Использование: python freelance_add.py <файл.json>")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"❌ Файл не найден: {json_path}")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    date_str = data.get("date", "").strip() or datetime.now().strftime("%d.%m.%Y")
    d = _parse_date(date_str)
    projects = [p for p in data.get("projects", []) if not p.get("_example")]

    if not projects:
        print("⚠️  Список проектов пуст. Ничего не добавлено.")
        sys.exit(0)

    print(f"📅 Дата: {date_str}")
    print(f"📋 Проектов к добавлению: {len(projects)}\n")

    records = []
    errors = 0
    for i, p in enumerate(projects, 1):
        missing = [k for k in ("project", "platform", "template") if not p.get(k)]
        if missing:
            print(f"  [{i}] ⚠️  Пропущено '{p.get('project', '?')}' — нет полей: {missing}")
            errors += 1
            continue
        rec = _build_record(p, d)
        records.append(rec)
        budget_info = f" | бюджет: {p.get('budget','?')} | ставка: {p.get('our_rate','?')}"
        print(f"  [{i}] {p['project']} / {p['platform']}{budget_info}")

    if not records:
        print("\n❌ Нет валидных записей.")
        sys.exit(1)

    print(f"\n💾 Записываю {len(records)} проектов в PostgreSQL...")
    inserted = 0
    skipped = 0
    with Database() as db:
        for rec in records:
            try:
                project_id = db.add_freelance(rec)
                log.info(f"add_freelance | id={project_id} | {rec['project_title']} | "
                         f"{rec['platform']} | {rec['status']}")
                inserted += 1
            except Exception as e:
                log.error(f"add_freelance ERROR: {e} | {rec.get('project_title')} | "
                          f"{rec.get('url')}")
                print(f"  ⚠️  Пропущено '{rec.get('project_title')}': {e}")
                skipped += 1

    print(f"\n{'─'*40}")
    print(f"✅ Добавлено:  {inserted}")
    if skipped:
        print(f"⚠️  Пропущено: {skipped}")
    if errors:
        print(f"❌ Ошибок JSON: {errors}")
    print(f"{'─'*40}")
    print(f"\nНе забудь очистить '{json_path.name}' — установить projects: [] для следующей сессии.")

    sys.exit(0 if (skipped + errors) == 0 else 1)


if __name__ == "__main__":
    main()
