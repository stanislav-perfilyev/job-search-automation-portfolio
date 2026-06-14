#!/usr/bin/env python3
"""
Add a single vacancy row to Google Sheets via Sheets API v4.

Usage:
  python add_vacancy.py --vacancy "C++ Developer" --company "Acme" \
    --url "https://example.com/job/123" --source "hh.kz" --template "B" \
    --date "14.06.2026"

Sources:  hh.ru | hh.kz | Habr Career | корп. сайт | LinkedIn | Telegram
Templates: A | B | C
Date:     DD.MM.YYYY (defaults to today)

Required env vars:
  SPREADSHEET_ID  — Google Sheets spreadsheet ID
  (auth via sheets_key.json or GOOGLE_SERVICE_ACCOUNT_JSON env var)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# ── Config ──────────────────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SHEET_NAME     = "Вакансии"
KEY_FILE       = Path(__file__).parent / "sheets_key.json"
SCOPES         = ["https://www.googleapis.com/auth/spreadsheets"]

if not SPREADSHEET_ID:
    sys.exit("ERROR: SPREADSHEET_ID environment variable must be set.")
if not KEY_FILE.exists():
    sys.exit(f"ERROR: {KEY_FILE} not found. See sheets_key.json.example.")

# Columns: A=Vacancy B=Company C=URL D=Source E=Template
#          F=Date hh.ru G=Date corp-site H=Date social I=Status J=Comment K=HR contact

def get_token():
    creds = service_account.Credentials.from_service_account_file(
        str(KEY_FILE), scopes=SCOPES
    )
    creds.refresh(Request())
    return creds.token

def append_row(token, row_data):
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
        f"/values/{SHEET_NAME}!A:K:append"
        f"?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    )
    body = {"values": [row_data]}
    r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=body)
    r.raise_for_status()
    return r.json()

def main():
    parser = argparse.ArgumentParser(description="Add vacancy to Google Sheets")
    parser.add_argument("--vacancy",  required=True)
    parser.add_argument("--company",  required=True)
    parser.add_argument("--url",      required=True)
    parser.add_argument("--source",   required=True,
                        help="hh.ru | hh.kz | Habr Career | корп. сайт | LinkedIn | Telegram")
    parser.add_argument("--template", default="B", help="Cover letter template A/B/C")
    parser.add_argument("--date",     default=datetime.today().strftime("%d.%m.%Y"))
    parser.add_argument("--status",   default="ожидание")
    parser.add_argument("--comment",  default="")
    parser.add_argument("--hr",       default="")
    args = parser.parse_args()

    source_lower = args.source.lower().strip()
    date_f = date_g = date_h = ""
    if "hh" in source_lower:
        date_f = args.date
    elif "корп" in source_lower:
        date_g = args.date
    elif "linkedin" in source_lower or "соцс" in source_lower or "telegram" in source_lower:
        date_h = args.date
    else:
        date_f = args.date

    row = [
        args.vacancy, args.company, args.url, args.source, args.template,
        date_f, date_g, date_h, args.status, args.comment, args.hr,
    ]

    print(f"🔐 Getting token...")
    token = get_token()
    print(f"📊 Appending row...")
    result = append_row(token, row)
    updated = result.get("updates", {}).get("updatedRange", "?")
    print(f"✅ Added to {updated}")
    print(f"   {args.vacancy} | {args.company} | {args.source} | {args.date} | {args.status}")

if __name__ == "__main__":
    main()
