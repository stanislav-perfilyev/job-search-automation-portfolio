#!/usr/bin/env python3
"""
init_db.py — создаёт таблицы PostgreSQL для job-search проекта.

Использование:
  python init_db.py

Env vars:
  DATABASE_URL — postgresql://user:pass@host:5432/dbname
"""

import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extensions import connection as PgConnection

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ── DDL ──────────────────────────────────────────────────────────────────────

DDL = """
-- ── 1. Вакансии с hh.kz / Habr Career ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS vacancies (
    id            SERIAL PRIMARY KEY,
    date          DATE           NOT NULL,
    title         TEXT           NOT NULL,
    company       TEXT           NOT NULL,
    url           TEXT           NOT NULL,
    salary_min    INTEGER,
    salary_max    INTEGER,
    currency      VARCHAR(10)    DEFAULT 'KZT',
    source        VARCHAR(50)    NOT NULL,           -- hh.kz | Habr Career | корп.сайт | ...
    status        VARCHAR(20)    NOT NULL DEFAULT 'applied'
                                 CHECK (status IN ('new','applied','interview',
                                                   'offer','rejected','ignored')),
    template_used TEXT,                              -- A | B | C
    skill_gaps    TEXT,                              -- чего не хватало (из колонки L)
    notes         TEXT,
    created_at    TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    CONSTRAINT vacancies_url_unique UNIQUE (url)
);

CREATE INDEX IF NOT EXISTS idx_vacancies_date   ON vacancies (date DESC);
CREATE INDEX IF NOT EXISTS idx_vacancies_status ON vacancies (status);
CREATE INDEX IF NOT EXISTS idx_vacancies_source ON vacancies (source);

-- ── 2. Фриланс-отклики (Upwork / FL.ru / Kwork) ──────────────────────────
CREATE TABLE IF NOT EXISTS freelance_projects (
    id              SERIAL PRIMARY KEY,
    date            DATE           NOT NULL,
    platform        VARCHAR(30)    NOT NULL,         -- Upwork | FL.ru | Kwork | ...
    project_title   TEXT           NOT NULL,
    client          TEXT,
    url             TEXT,
    budget          NUMERIC(12,2),
    our_rate        NUMERIC(12,2),
    connects_spent  INTEGER        DEFAULT 0,
    template_used   TEXT,
    comment         TEXT,
    status          VARCHAR(20)    NOT NULL DEFAULT 'sent'
                                   CHECK (status IN ('sent','viewed','interview',
                                                     'contract','rejected','closed')),
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),

    CONSTRAINT freelance_url_unique UNIQUE (url)
);

CREATE INDEX IF NOT EXISTS idx_freelance_date     ON freelance_projects (date DESC);
CREATE INDEX IF NOT EXISTS idx_freelance_platform ON freelance_projects (platform);
CREATE INDEX IF NOT EXISTS idx_freelance_status   ON freelance_projects (status);

-- ── 3. Ежедневная статистика ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_stats (
    date                DATE    PRIMARY KEY,
    vacancies_found     INTEGER DEFAULT 0,
    applied_count       INTEGER DEFAULT 0,
    freelance_sent      INTEGER DEFAULT 0,
    responses_received  INTEGER DEFAULT 0,
    interviews          INTEGER DEFAULT 0,
    notes               TEXT
);

-- ── 4. Лог изменений статусов (аудит) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS status_history (
    id          SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,   -- vacancy | freelance
    entity_id   INTEGER     NOT NULL,
    old_status  VARCHAR(20),
    new_status  VARCHAR(20) NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_entity ON status_history (entity_type, entity_id);
"""


def init_db(conn: PgConnection) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
    conn.commit()
    print("✅ Таблицы созданы (или уже существовали).")


def show_tables(conn: PgConnection) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tablename, pg_size_pretty(pg_total_relation_size(quote_ident(tablename)))
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        rows = cur.fetchall()
    print("\n📋 Таблицы в БД:")
    for name, size in rows:
        print(f"  {name:<30} {size}")


def main() -> None:
    if not DATABASE_URL:
        print("❌ DATABASE_URL не задан. Добавь в .env или export DATABASE_URL=...")
        sys.exit(1)

    print(f"🔌 Подключаюсь к PostgreSQL...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ Не удалось подключиться: {e}")
        sys.exit(1)

    try:
        init_db(conn)
        show_tables(conn)
    finally:
        conn.close()

    print("\n✅ Готово! БД инициализирована.")


if __name__ == "__main__":
    main()
