#!/usr/bin/env python3
"""
Добавляет строку в Google Sheets "Вакансии" через Sheets API v4.

Использование:
  python add_vacancy.py --vacancy "C++ разработчик" --company "Компания" \
    --url "https://example.com" --source "hh.ru" --template "шаблон С" \
    --date "13.06.2026"

Источники: hh.ru | корп. сайт | LinkedIn | hh.kz
Шаблоны:   шаблон А | шаблон В | шаблон С
Дата:      формат DD.MM.YYYY (по умолчанию — сегодня)
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# ── Константы ──────────────────────────────────────────────────────────────
import os as _os
SPREADSHEET_ID        = _os.environ.get("SPREADSHEET_ID", "1ri78JxboQ477L7nLOmXJupe2ALORwKqbh-jiKuAL8XE")
CURATOR_SPREADSHEET_ID = _os.environ.get("CURATOR_SPREADSHEET_ID", "13Y0fswfjgaCfrOj52Gv5Q-4ws9i7HtvlvSZPv1cyG9U")
SHEET_NAME     = "Вакансии"
KEY_FILE       = Path(__file__).parent / "sheets_key.json"
SCOPES         = ["https://www.googleapis.com/auth/spreadsheets"]

# Столбцы: A=Вакансия B=Компания C=Ссылка D=Источник E=Шаблон
#          F=Дата hh.ru G=Дата корп.сайт H=Дата соцсети I=Статус J=Комментарий K=Контакт HR

SOURCE_TO_COL = {
    "hh.ru":      "F",
    "hh.kz":      "F",
    "корп. сайт": "G",
    "linkedin":   "H",
    "соцсети":    "H",
}

def get_token():
    creds = service_account.Credentials.from_service_account_file(
        str(KEY_FILE), scopes=SCOPES
    )
    creds.refresh(Request())
    return creds.token

def get_last_row(token):
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
        f"/values/{SHEET_NAME}!A:A"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    values = r.json().get("values", [])
    return len(values)

def append_row(token, spreadsheet_id, row_data):
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
        f"/values/{SHEET_NAME}!A:K:append"
        f"?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    )
    body = {"values": [row_data]}
    r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    r.raise_for_status()
    return r.json()

def main():
    parser = argparse.ArgumentParser(description="Добавить вакансию в Google Sheets")
    parser.add_argument("--vacancy",  required=True,  help="Название вакансии")
    parser.add_argument("--company",  required=True,  help="Компания")
    parser.add_argument("--url",      required=True,  help="Ссылка на вакансию")
    parser.add_argument("--source",   required=True,  help="Источник: hh.ru | корп. сайт | LinkedIn | hh.kz")
    parser.add_argument("--template", default="шаблон С", help="Шаблон письма (по умолчанию: шаблон С)")
    parser.add_argument("--date",     default=datetime.today().strftime("%d.%m.%Y"), help="Дата отклика DD.MM.YYYY")
    parser.add_argument("--status",   default="ожидание", help="Статус (по умолчанию: ожидание)")
    parser.add_argument("--comment",  default="",     help="Комментарий")
    parser.add_argument("--hr",       default="",     help="Контакт HR")
    args = parser.parse_args()

    source_lower = args.source.lower().strip()

    # Определяем в какой столбец дата
    date_f = ""  # hh.ru / hh.kz
    date_g = ""  # корп. сайт
    date_h = ""  # соцсети / LinkedIn
    if "hh" in source_lower:
        date_f = args.date
    elif "корп" in source_lower:
        date_g = args.date
    elif "linkedin" in source_lower or "соцс" in source_lower:
        date_h = args.date
    else:
        date_f = args.date  # fallback

    # 11 столбцов: A B C D E F G H I J K
    row = [
        args.vacancy,   # A
        args.company,   # B
        args.url,       # C
        args.source,    # D
        args.template,  # E
        date_f,         # F — Дата hh.ru
        date_g,         # G — Дата корп.сайт
        date_h,         # H — Дата соцсети
        args.status,    # I
        args.comment,   # J
        args.hr,        # K
    ]

    print(f"🔐 Получаю токен...")
    token = get_token()

    print(f"📊 Добавляю строку в основную таблицу...")
    result = append_row(token, SPREADSHEET_ID, row)
    updated = result.get("updates", {}).get("updatedRange", "?")
    print(f"✅ Основная таблица: {updated}")

    print(f"📊 Добавляю строку в таблицу куратора...")
    result2 = append_row(token, CURATOR_SPREADSHEET_ID, row)
    updated2 = result2.get("updates", {}).get("updatedRange", "?")
    print(f"✅ Таблица куратора: {updated2}")

    print(f"   {args.vacancy} | {args.company} | {args.source} | {args.date} | {args.status}")

if __name__ == "__main__":
    main()
