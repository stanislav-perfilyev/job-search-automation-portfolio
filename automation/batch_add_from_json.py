#!/usr/bin/env python3
"""
batch_add_from_json.py — пакетное добавление откликов из JSON в PostgreSQL (primary)
и Google Sheets куратора (mirror).

Использование:
  python batch_add_from_json.py session_vacancies.json

Формат JSON:
  {
    "date": "14.06.2026",
    "vacancies": [
      {
        "vacancy":    "C++ разработчик",
        "company":    "Компания",
        "url":        "https://hh.kz/vacancy/...",
        "source":     "hh.kz",
        "template":   "B",
        "comment":    "",
        "skill_gaps": "Boost, Docker, CUDA"
      }
    ]
  }
"""

import json
import sys
import time
from datetime import datetime, date
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

import os as _os
# Sheets используется ТОЛЬКО для зеркала куратора (read-only здесь не нужен)
CURATOR_SPREADSHEET_ID = _os.environ.get("CURATOR_SPREADSHEET_ID", "13Y0fswfjgaCfrOj52Gv5Q-4ws9i7HtvlvSZPv1cyG9U")
SHEET_NAME = "Вакансии"
KEY_FILE   = Path(__file__).parent / "sheets_key.json"
SCOPES     = ["https://www.googleapis.com/auth/spreadsheets"]

_RETRY_ATTEMPTS = 3
_RETRY_DELAY    = 2.0


# ── Google Sheets auth (только для куратора) ─────────────────────────────────

def get_sheets_token() -> str:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GRequest
    creds = service_account.Credentials.from_service_account_file(
        str(KEY_FILE), scopes=SCOPES
    )
    creds.refresh(GRequest())
    return creds.token


def build_curator_row(v: dict, date_str: str) -> list:
    """12 ячеек A:L для таблицы куратора."""
    source_lower = v["source"].lower().strip()
    date_f = date_g = date_h = ""
    if "hh" in source_lower:
        date_f = date_str
    elif "корп" in source_lower:
        date_g = date_str
    elif "linkedin" in source_lower or "соцс" in source_lower:
        date_h = date_str
    else:
        date_f = date_str

    template = v["template"].strip()
    if not template.startswith("шаблон"):
        template = f"шаблон {template}"

    return [
        v["vacancy"],
        v["company"],
        v["url"],
        v["source"],
        template,
        date_f,
        date_g,
        date_h,
        v.get("status", "ожидание"),
        v.get("comment", ""),
        v.get("hr", ""),
        v.get("skill_gaps", ""),
    ]


def append_to_curator(token: str, rows: list) -> str:
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{CURATOR_SPREADSHEET_ID}"
        f"/values/{SHEET_NAME}!A:L:append"
        f"?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    )
    delay = _RETRY_DELAY
    last_err = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"values": rows},
                timeout=30,
            )
            if r.status_code == 429:
                retry_after = float(r.headers.get("Retry-After", delay))
                time.sleep(min(retry_after, 60))
                continue
            r.raise_for_status()
            return r.json().get("updates", {}).get("updatedRange", "?")
        except requests.RequestException as e:
            last_err = e
            if attempt < _RETRY_ATTEMPTS:
                time.sleep(delay)
                delay *= 2
    raise RuntimeError(f"Sheets API недоступен: {last_err}")


# ── Основная логика ───────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Использование: python batch_add_from_json.py <файл.json>")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"Файл не найден: {json_path}")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    date_str  = data.get("date", "").strip() or datetime.now().strftime("%d.%m.%Y")
    vacancies = [v for v in data.get("vacancies", []) if not v.get("_example")]

    if not vacancies:
        print("Список вакансий пуст. Ничего не добавлено.")
        sys.exit(0)

    print(f"Дата: {date_str}  |  Вакансий: {len(vacancies)}\n")

    # ── Валидация ─────────────────────────────────────────────────────────────
    valid = []
    errors = 0
    for i, v in enumerate(vacancies, 1):
        missing = [k for k in ("vacancy", "company", "url", "source", "template") if not v.get(k)]
        if missing:
            print(f"  [{i}] Пропуск '{v.get('company', '?')}' — нет полей: {missing}")
            errors += 1
            continue
        valid.append(v)
        print(f"  [{i}] {v['vacancy']} / {v['company']}")

    if not valid:
        print("\nНет валидных строк.")
        sys.exit(1)

    # Парсим дату
    try:
        parsed_date = datetime.strptime(date_str, "%d.%m.%Y").date()
    except ValueError:
        parsed_date = date.today()

    # ── 1. PostgreSQL (primary — source of truth) ─────────────────────────────
    print(f"\n📦 Пишу {len(valid)} записей в PostgreSQL...")
    from db import Database
    pg_ok = 0
    pg_errors = 0
    try:
        with Database() as db:
            for v in valid:
                try:
                    db.add_vacancy({
                        "date":         parsed_date,
                        "title":        v["vacancy"],
                        "company":      v["company"],
                        "url":          v["url"],
                        "source":       v["source"],
                        "status":       v.get("status", "applied"),
                        "template_used": f"шаблон {v['template']}" if not v["template"].startswith("шаблон") else v["template"],
                        "skill_gaps":   v.get("skill_gaps"),
                        "notes":        v.get("comment"),
                    })
                    pg_ok += 1
                except Exception as e:
                    print(f"  ⚠️  PG ошибка для {v['company']}: {e}")
                    pg_errors += 1
    except Exception as e:
        print(f"  ❌ Нет подключения к PostgreSQL: {e}")
        print("     Данные НЕ сохранены в БД. Проверь DATABASE_URL в .env")
        sys.exit(1)

    print(f"  ✅ PostgreSQL: {pg_ok} добавлено, {pg_errors} ошибок")

    # ── 2. Sheets куратора (mirror — только зеркало) ──────────────────────────
    print(f"\n🪞 Зеркалирую {len(valid)} строк в таблицу куратора...")
    curator_ok = True
    try:
        if not KEY_FILE.exists():
            print("  ⏭  sheets_key.json не найден — куратор пропущен")
        elif not CURATOR_SPREADSHEET_ID:
            print("  ⏭  CURATOR_SPREADSHEET_ID не задан — пропущен")
        else:
            token = get_sheets_token()
            curator_rows = [build_curator_row(v, date_str) for v in valid]
            rng = append_to_curator(token, curator_rows)
            print(f"  ✅ Куратор: {rng}")
    except Exception as e:
        print(f"  ⚠️  Куратор не записан: {e} (данные в PG уже сохранены)")
        curator_ok = False

    # ── Итог ──────────────────────────────────────────────────────────────────
    print(f"\n{'─'*40}")
    print(f"PostgreSQL:  {pg_ok}/{len(valid)} записей")
    print(f"Куратор:     {'✅' if curator_ok else '⚠️  пропущен'}")
    if errors:
        print(f"Пропущено:   {errors} (невалидные)")
    print(f"{'─'*40}")
    print(f"\nОчисти '{json_path.name}' — установи vacancies: [] для следующей сессии.")

    sys.exit(0 if pg_ok == len(valid) else 1)


if __name__ == "__main__":
    main()
