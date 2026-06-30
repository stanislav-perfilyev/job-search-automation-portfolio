#!/usr/bin/env python3
"""
migrate_from_sheets.py — мигрирует данные из Google Sheets в PostgreSQL.

Читает:
  - "Вакансии" (SPREADSHEET_ID)  → таблица vacancies
  - "Проекты"  (FREELANCE_SPREADSHEET_ID) → таблица freelance_projects

Использование:
  python migrate_from_sheets.py              # мигрировать всё
  python migrate_from_sheets.py --dry-run    # показать что будет, не писать в БД
  python migrate_from_sheets.py --only vac   # только вакансии
  python migrate_from_sheets.py --only fl    # только фриланс

Env vars:
  DATABASE_URL
  SPREADSHEET_ID
  FREELANCE_SPREADSHEET_ID
  GOOGLE_SERVICE_ACCOUNT_JSON  (base64, для CI) или sheets_key.json рядом
"""

import argparse
import base64
import os
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from db import Database

# ── Константы ────────────────────────────────────────────────────────────────

SPREADSHEET_ID          = os.environ.get("SPREADSHEET_ID", "")
FREELANCE_SPREADSHEET_ID = os.environ.get("FREELANCE_SPREADSHEET_ID", "")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Маппинг статусов из Sheets → PostgreSQL CHECK constraint
VACANCY_STATUS_MAP = {
    "ожидание": "applied",
    "отклик":   "applied",
    "applied":  "applied",
    "интервью": "interview",
    "interview":"interview",
    "оффер":    "offer",
    "offer":    "offer",
    "отказ":    "rejected",
    "отказали": "rejected",
    "rejected": "rejected",
    "ignored":  "ignored",
    "new":      "new",
}

FREELANCE_STATUS_MAP = {
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


# ── Google Sheets helpers ─────────────────────────────────────────────────────

def _get_key_file() -> Path:
    env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            decoded = base64.b64decode(env_json)
        except Exception:
            decoded = env_json.encode()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="wb")
        tmp.write(decoded)
        tmp.close()
        return Path(tmp.name)
    return Path(__file__).parent / "sheets_key.json"


def get_token() -> str:
    creds = service_account.Credentials.from_service_account_file(
        str(_get_key_file()), scopes=SCOPES
    )
    creds.refresh(Request())
    return creds.token


def fetch_sheet(token: str, sheet_id: str, range_: str) -> list[list[str]]:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{range_}"
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json().get("values", [])


# ── Парсинг ───────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date | None:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def _parse_salary(s: str) -> tuple[int | None, int | None]:
    """Из строки вроде '300000-500000' или '400 000' → (min, max)."""
    if not s:
        return None, None
    digits = re.findall(r"\d[\d\s]*", s)
    nums = [int(d.replace(" ", "")) for d in digits if d.strip()]
    if not nums:
        return None, None
    if len(nums) >= 2:
        return min(nums), max(nums)
    return nums[0], None


def _map_status(raw: str, mapping: dict) -> str:
    return mapping.get(raw.lower().strip(), "applied")


def parse_vacancy_row(row: list[str]) -> dict[str, Any] | None:
    """
    Колонки Google Sheets "Вакансии" (A:L):
      A=Вакансия B=Компания C=URL D=Источник E=Шаблон
      F=ДатаHH   G=ДатаКорп H=ДатаСоцсети
      I=Статус   J=Комментарий K=HR L=Пробелы
    """
    row = row + [""] * (12 - len(row))  # pad to 12 cols
    title   = row[0].strip()
    company = row[1].strip()
    url     = row[2].strip()
    if not title or not company:
        return None

    # Дата — берём первую непустую из F/G/H
    date_str = row[5] or row[6] or row[7]
    d = _parse_date(date_str) if date_str else date.today()

    source   = row[3].strip() or "hh.kz"
    template = row[4].strip()
    if template.lower().startswith("шаблон"):
        template = template.split()[-1]  # "шаблон B" → "B"

    return {
        "date":          d,
        "title":         title,
        "company":       company,
        "url":           url or f"no-url-{title[:30]}-{company[:20]}",
        "source":        source,
        "status":        _map_status(row[8], VACANCY_STATUS_MAP),
        "template_used": template or None,
        "notes":         row[9].strip() or None,
        "skill_gaps":    row[11].strip() or None,
    }


def parse_freelance_row(row: list[str]) -> dict[str, Any] | None:
    """
    Колонки Google Sheets "Проекты" (A:K):
      A=Проект  B=Клиент  C=URL  D=Платформа  E=Шаблон
      F=Бюджет  G=НашаСтавка  H=Дата  I=Статус  J=Комментарий  K=Connects
    """
    row = row + [""] * (11 - len(row))
    title    = row[0].strip()
    platform = row[3].strip() or "Upwork"
    if not title:
        return None

    d = _parse_date(row[7]) if row[7] else date.today()

    budget_min, _  = _parse_salary(row[5])
    our_rate, _    = _parse_salary(row[6])
    try:
        connects = int(row[10].strip()) if row[10].strip() else 0
    except ValueError:
        connects = 0

    url = row[2].strip() or None

    return {
        "date":           d,
        "platform":       platform,
        "project_title":  title,
        "client":         row[1].strip() or None,
        "url":            url,
        "budget":         budget_min,
        "our_rate":       our_rate,
        "connects_spent": connects,
        "template_used":  row[4].strip() or None,
        "comment":        row[9].strip() or None,
        "status":         _map_status(row[8], FREELANCE_STATUS_MAP),
    }


# ── Миграция ──────────────────────────────────────────────────────────────────

def migrate_vacancies(db: Database, token: str, dry_run: bool) -> tuple[int, int, int]:
    """Возвращает (total_rows, inserted, skipped)."""
    if not SPREADSHEET_ID:
        print("⚠️  SPREADSHEET_ID не задан — пропускаю вакансии")
        return 0, 0, 0

    print("📥 Читаю лист 'Вакансии'...")
    rows = fetch_sheet(token, SPREADSHEET_ID, "Вакансии!A:L")
    data_rows = rows[1:] if rows else []  # пропускаем заголовок
    print(f"   Строк: {len(data_rows)}")

    inserted = skipped = 0
    for i, row in enumerate(data_rows, 2):
        parsed = parse_vacancy_row(row)
        if parsed is None:
            skipped += 1
            continue
        if dry_run:
            print(f"   [DRY] {parsed['date']} | {parsed['title'][:40]} | {parsed['company']}")
            inserted += 1
            continue
        try:
            vid = db.add_vacancy(parsed)
            inserted += 1
            if inserted <= 3:
                print(f"   ✓ #{vid} {parsed['title'][:40]}")
        except Exception as e:
            print(f"   ⚠️  Строка {i}: {e}", file=sys.stderr)
            skipped += 1

    return len(data_rows), inserted, skipped


def migrate_freelance(db: Database, token: str, dry_run: bool) -> tuple[int, int, int]:
    if not FREELANCE_SPREADSHEET_ID:
        print("⚠️  FREELANCE_SPREADSHEET_ID не задан — пропускаю фриланс")
        return 0, 0, 0

    print("📥 Читаю лист 'Проекты'...")
    rows = fetch_sheet(token, FREELANCE_SPREADSHEET_ID, "Проекты!A:K")
    data_rows = rows[1:] if rows else []
    print(f"   Строк: {len(data_rows)}")

    inserted = skipped = 0
    for i, row in enumerate(data_rows, 2):
        parsed = parse_freelance_row(row)
        if parsed is None:
            skipped += 1
            continue
        if dry_run:
            print(f"   [DRY] {parsed['date']} | {parsed['project_title'][:40]} | {parsed['platform']}")
            inserted += 1
            continue
        try:
            fid = db.add_freelance(parsed)
            inserted += 1
            if inserted <= 3:
                print(f"   ✓ #{fid} {parsed['project_title'][:40]}")
        except Exception as e:
            print(f"   ⚠️  Строка {i}: {e}", file=sys.stderr)
            skipped += 1

    return len(data_rows), inserted, skipped


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Миграция Sheets → PostgreSQL")
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать что будет мигрировано, не писать в БД")
    parser.add_argument("--only", choices=["vac", "fl"],
                        help="Мигрировать только вакансии (vac) или фриланс (fl)")
    args = parser.parse_args()

    if args.dry_run:
        print("🔍 DRY RUN — реальной записи в БД не будет\n")

    print("🔐 Получаю Google токен...")
    token = get_token()
    print("   ✓")

    db = Database() if not args.dry_run else None

    total_v = ins_v = skip_v = 0
    total_f = ins_f = skip_f = 0

    if args.only in (None, "vac"):
        total_v, ins_v, skip_v = migrate_vacancies(db, token, args.dry_run)
        print(f"   → вставлено: {ins_v}, пропущено: {skip_v}\n")

    if args.only in (None, "fl"):
        total_f, ins_f, skip_f = migrate_freelance(db, token, args.dry_run)
        print(f"   → вставлено: {ins_f}, пропущено: {skip_f}\n")

    if db:
        db.close()

    print("─" * 40)
    print(f"✅ Миграция завершена{'  [DRY RUN]' if args.dry_run else ''}:")
    print(f"   Вакансии:  {ins_v}/{total_v}")
    print(f"   Фриланс:   {ins_f}/{total_f}")


if __name__ == "__main__":
    main()
