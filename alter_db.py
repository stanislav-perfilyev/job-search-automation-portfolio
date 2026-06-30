#!/usr/bin/env python3
"""
alter_db.py — исправляет схему таблиц в Neon PostgreSQL.

Расширяет ограниченные VARCHAR поля, которые были созданы слишком узкими.
Безопасно запускать повторно (использует ALTER COLUMN IF EXISTS подход).

Использование:
  python alter_db.py
"""

import os
import sys
from pathlib import Path

import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL", "")

ALTER_STATEMENTS = [
    # template_used: могло быть создано как VARCHAR(10) — теперь TEXT
    "ALTER TABLE vacancies ALTER COLUMN template_used TYPE TEXT",
    "ALTER TABLE freelance_projects ALTER COLUMN template_used TYPE TEXT",
    # currency: расширяем на случай длинных значений
    "ALTER TABLE vacancies ALTER COLUMN currency TYPE VARCHAR(20)",
    # source: расширяем с 50 до 100 (URL источника может быть длинным)
    "ALTER TABLE vacancies ALTER COLUMN source TYPE VARCHAR(100)",
    # platform: расширяем с 30 до 50
    "ALTER TABLE freelance_projects ALTER COLUMN platform TYPE VARCHAR(50)",
]

def main():
    if not DATABASE_URL:
        print("❌ DATABASE_URL не задан в .env")
        sys.exit(1)

    print("🔌 Подключаюсь к PostgreSQL...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        sys.exit(1)

    cur = conn.cursor()
    ok = 0
    errors = 0

    for stmt in ALTER_STATEMENTS:
        try:
            cur.execute(stmt)
            print(f"  ✅ {stmt}")
            ok += 1
        except Exception as e:
            # Если тип уже TEXT — ошибка "cannot alter to same type"
            if "does not exist" in str(e) or "same type" in str(e):
                print(f"  ⏭  Пропущено (уже OK): {stmt}")
            else:
                print(f"  ❌ Ошибка: {e}")
                print(f"     SQL: {stmt}")
                errors += 1

    cur.close()
    conn.close()

    print(f"\n{'─'*50}")
    print(f"Изменено: {ok}   Ошибок: {errors}")

    if errors:
        sys.exit(1)
    else:
        print("✅ Схема исправлена — можно запускать migrate_from_sheets.py")


if __name__ == "__main__":
    main()
