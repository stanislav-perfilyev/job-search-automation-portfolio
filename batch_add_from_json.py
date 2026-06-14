#!/usr/bin/env python3
"""
batch_add_from_json.py — пакетное добавление откликов из JSON-файла в Google Sheets.

Использование:
  python batch_add_from_json.py session_vacancies.json

Формат JSON:
  {
    "date": "14.06.2026",          # если пусто — берётся сегодняшняя дата
    "vacancies": [
      {
        "vacancy":  "C++ разработчик",
        "company":  "Компания",
        "url":      "https://hh.kz/vacancy/...",
        "source":   "hh.kz",       # hh.kz | hh.ru | Habr Career | корп. сайт | LinkedIn | Telegram
        "template": "B",           # A | B | C
        "comment":  ""             # опционально, идёт в колонку J
      }
    ]
  }

Запускать в конце каждой сессии. После успешного запуска — очистить vacancies до [].
Заменяет устаревший batch_add_session.py (который требовал переписывать скрипт каждую сессию).
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Использование: python batch_add_from_json.py <файл.json>")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"❌ Файл не найден: {json_path}")
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    date_str = data.get("date", "").strip() or datetime.now().strftime("%d.%m.%Y")
    vacancies = [v for v in data.get("vacancies", []) if not v.get("_example")]

    if not vacancies:
        print("⚠️  Список вакансий пуст. Ничего не добавлено.")
        sys.exit(0)

    print(f"📅 Дата: {date_str}")
    print(f"📋 Вакансий к добавлению: {len(vacancies)}\n")

    add_script = Path(__file__).parent / "add_vacancy.py"
    ok = 0
    errors = 0

    for i, v in enumerate(vacancies, 1):
        # валидация обязательных полей
        missing = [k for k in ("vacancy", "company", "url", "source", "template") if not v.get(k)]
        if missing:
            print(f"  [{i}/{len(vacancies)}] ⚠️  Пропущено {v.get('company', '?')} — нет полей: {missing}")
            errors += 1
            continue

        cmd = [
            sys.executable, str(add_script),
            "--vacancy",  v["vacancy"],
            "--company",  v["company"],
            "--url",      v["url"],
            "--source",   v["source"],
            "--template", v["template"],
            "--date",     date_str,
        ]
        if v.get("comment"):
            cmd += ["--comment", v["comment"]]

        label = f"{v['vacancy']} / {v['company']}"
        print(f"  [{i}/{len(vacancies)}] {label}... ", end="", flush=True)

        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            print("✓")
            ok += 1
        else:
            print(f"❌ ОШИБКА")
            print(f"     stdout: {result.stdout.strip()}")
            print(f"     stderr: {result.stderr.strip()}")
            errors += 1

    print(f"\n{'─'*40}")
    print(f"✅ Добавлено:  {ok}")
    if errors:
        print(f"❌ Ошибок:    {errors}")
    print(f"{'─'*40}")

    if ok > 0:
        print(f"\nНе забудь очистить '{json_path.name}' — установить vacancies: [] для следующей сессии.")

    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
