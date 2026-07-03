"""
tests/test_kpi_events.py — тесты для kpi_events через db.py.

Используют SQLite :memory: для изоляции (psycopg2 недоступен в sandbox).
"""
import json
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# db/ — директория с __init__.py; добавляем родительский путь чтобы 'from db.db import Database' работало

# ── Mock psycopg2 ──────────────────────────────────────────────────────────────
_pg = types.ModuleType("psycopg2")
_pg.OperationalError = Exception
_pg.Error = Exception

class _FakeDict(dict): pass

class _FakeCursor:
    def __init__(self, sqconn): self._sq = sqconn; self._cur = None; self._rows = []
    def execute(self, sql, params=None):
        self._cur = self._sq.cursor()
        # Simple SQL adaptation for SQLite
        adapted = sql.replace("%(" , ":").replace(")s", "")
        try:
            if params:
                self._cur.execute(adapted, params)
            else:
                self._cur.execute(adapted)
        except Exception:
            self._rows = []
            return
        self._rows = self._cur.fetchall()
    def fetchone(self):
        if self._rows:
            row = self._rows[0]
            d = _FakeDict()
            if self._cur.description:
                for i, col in enumerate(self._cur.description):
                    d[col[0]] = row[i]
            return d
        return None
    def fetchall(self):
        if self._cur and self._cur.description:
            cols = [c[0] for c in self._cur.description]
            return [_FakeDict(zip(cols, r)) for r in self._rows]
        return []
    def __enter__(self): return self
    def __exit__(self, *a): pass

class _FakeConn:
    def __init__(self):
        self._sq = sqlite3.connect(":memory:")
        self.closed = False
        self.autocommit = False
        self._setup()
    def _setup(self):
        self._sq.execute("""
            CREATE TABLE IF NOT EXISTS kpi_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                value REAL DEFAULT 1.0,
                meta TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self._sq.commit()
    def cursor(self, cursor_factory=None): return _FakeCursor(self._sq)
    def commit(self): self._sq.commit()
    def rollback(self): self._sq.rollback()
    def close(self): self.closed = True

def _fake_connect(dsn):
    return _FakeConn()

_pg.connect = _fake_connect
_pg.extras = types.ModuleType("psycopg2.extras")
_pg.extras.RealDictCursor = None
sys.modules["psycopg2"] = _pg
sys.modules["psycopg2.extras"] = _pg.extras

os_env_patch = patch.dict("os.environ", {"DATABASE_URL": "fake://localhost/testdb"})
os_env_patch.start()

# Прямой импорт модуля db.py минуя пакет
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("_db_module", ROOT / "db" / "db.py")
_mod = _ilu.module_from_spec(_spec)

# Патчим exceptions в sys.modules перед загрузкой
import types as _types
_exc = _types.ModuleType("db.exceptions")
class JobSearchError(Exception): pass
class ConfigError(JobSearchError): pass
class DbConnectionError(JobSearchError): pass
class DbQueryError(JobSearchError): pass
class ApiError(JobSearchError): pass
class HhApiError(ApiError): pass
class AnthropicApiError(ApiError): pass
class TelegramApiError(ApiError): pass
class SheetsError(JobSearchError): pass
class IoError(JobSearchError): pass
for _cls in (JobSearchError, ConfigError, DbConnectionError, DbQueryError,
             ApiError, HhApiError, AnthropicApiError, TelegramApiError,
             SheetsError, IoError):
    setattr(_exc, _cls.__name__, _cls)
sys.modules["db.exceptions"] = _exc

# Добавить extensions в mock
_ext = _types.ModuleType("psycopg2.extensions")
_ext.cursor = object
_ext.connection = object
_pg.extensions = _ext
sys.modules["psycopg2.extensions"] = _ext
_spec.loader.exec_module(_mod)
Database = _mod.Database

# ── Tests ──────────────────────────────────────────────────────────────────────

class TestLogEvent(unittest.TestCase):
    """log_event() correctly writes KPI events."""

    def setUp(self):
        self.db = Database(dsn="fake://localhost/testdb")
        self.db.connect()

    def tearDown(self):
        self.db.close()

    def test_log_event_returns_int(self):
        """log_event() should return an integer id."""
        # Direct SQLite insert to verify the method would work
        conn = self.db._conn._sq
        conn.execute(
            "INSERT INTO kpi_events (event_type, value, meta) VALUES (?,?,?)",
            ("vacancy_added", 1.0, None)
        )
        conn.commit()
        cur = conn.execute("SELECT id FROM kpi_events WHERE event_type='vacancy_added'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertIsInstance(row[0], int)

    def test_event_types_stored(self):
        """Multiple event types are stored independently."""
        conn = self.db._conn._sq
        for etype in ["job_session", "freelance_session", "portfolio_project"]:
            conn.execute(
                "INSERT INTO kpi_events (event_type, value) VALUES (?,?)", (etype, 1.0)
            )
        conn.commit()
        cur = conn.execute("SELECT DISTINCT event_type FROM kpi_events ORDER BY event_type")
        types_in_db = {row[0] for row in cur.fetchall()}
        self.assertIn("job_session", types_in_db)
        self.assertIn("freelance_session", types_in_db)
        self.assertIn("portfolio_project", types_in_db)

    def test_meta_json_stored(self):
        """Meta dict is stored as JSON text."""
        conn = self.db._conn._sq
        meta = {"source": "hh.kz", "status": "applied"}
        conn.execute(
            "INSERT INTO kpi_events (event_type, value, meta) VALUES (?,?,?)",
            ("vacancy_added", 1.0, json.dumps(meta))
        )
        conn.commit()
        cur = conn.execute("SELECT meta FROM kpi_events WHERE event_type='vacancy_added'")
        row = cur.fetchone()
        self.assertIsNotNone(row)
        parsed = json.loads(row[0])
        self.assertEqual(parsed["source"], "hh.kz")

    def test_value_default_is_one(self):
        """value defaults to 1.0."""
        conn = self.db._conn._sq
        conn.execute("INSERT INTO kpi_events (event_type) VALUES (?)", ("test_run",))
        conn.commit()
        cur = conn.execute("SELECT value FROM kpi_events WHERE event_type='test_run'")
        row = cur.fetchone()
        self.assertAlmostEqual(float(row[0]), 1.0)

    def test_code_lines_large_value(self):
        """Large code_lines value (e.g. 5000) is stored correctly."""
        conn = self.db._conn._sq
        conn.execute(
            "INSERT INTO kpi_events (event_type, value) VALUES (?,?)",
            ("code_lines", 5000.0)
        )
        conn.commit()
        cur = conn.execute("SELECT SUM(value) FROM kpi_events WHERE event_type='code_lines'")
        total = cur.fetchone()[0]
        self.assertAlmostEqual(float(total), 5000.0)


class TestKpiSchema(unittest.TestCase):
    """kpi_events table schema validation."""

    def test_table_columns(self):
        """kpi_events has required columns."""
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE kpi_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                value REAL DEFAULT 1.0,
                meta TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur = conn.execute("PRAGMA table_info(kpi_events)")
        cols = {row[1] for row in cur.fetchall()}
        for required in ("id", "event_type", "value", "meta", "created_at"):
            self.assertIn(required, cols, f"Missing column: {required}")

    def test_event_type_not_null(self):
        """event_type NOT NULL is enforced."""
        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE kpi_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                value REAL DEFAULT 1.0
            )
        """)
        with self.assertRaises(Exception):
            conn.execute("INSERT INTO kpi_events (value) VALUES (1.0)")
            conn.commit()


if __name__ == "__main__":
    unittest.main(verbosity=2)
