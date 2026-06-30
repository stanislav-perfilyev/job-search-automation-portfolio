# Job Search Automation

A production-grade job search automation system written in **Python 3.11 + C++17/Qt6**.  
All code follows senior engineering standards: custom exceptions, structured logging, RAII, OOP interfaces, unit tests.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Python Automation Layer                                             │
│  morning_brief.py  ·  session_prompt.py  ·  cover_letter.py        │
│  telegram_monitor.py · upwork_email_monitor.py · follow_up.py      │
├─────────────────────────────────────────────────────────────────────┤
│  FastAPI REST + WebSocket (app/)                                     │
│  /vacancies  /freelance  /stats  /health  /ws/updates               │
│  Deployed on Railway  ·  PostgreSQL (Neon)  ·  Redis cache          │
├─────────────────────────────────────────────────────────────────────┤
│  PostgreSQL  ·  Google Sheets mirror  ·  Telegram bot               │
├─────────────────────────────────────────────────────────────────────┤
│  C++ Portfolio (portfolio/)                                          │
│  Qt6 Dashboard  ·  WinAPI  ·  QML  ·  D-Bus  ·  MIL-STD-1553      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## C++ Portfolio

| Project | Tech | Highlights |
|---|---|---|
| **[Qt Job Dashboard](portfolio/qt-job-dashboard/)** | Qt6, C++17, SQLite/PostgreSQL, QtCharts | QAbstractTableModel, QSortFilterProxyModel, custom exceptions, DiagnosticsDialog, RAII, 18 tests |
| **[WinAPI Showcase](portfolio/winapi_showcase/)** | C++17, WinAPI | ProcessMonitor, FileWatcher, Named Pipe IPC; RAII handles, 9 tests |
| **[QML System Monitor](portfolio/qml_system_monitor/)** | Qt6, QML, C++ backend | Live CPU/RAM/disk charts, abstract ISystemStats, 7 tests |
| **[D-Bus Service](portfolio/dbus_service/)** | C++17, Qt D-Bus | SystemInfoService, typed error signals, client + server, 5 tests |
| **[DAQ Bug Fix](portfolio/daq-bugfix/)** | C++, multithreading | Fixed race condition in a production DAQ data collection system |
| **[MIL-STD-1553 Analyzer](portfolio/mil1553_analyzer/)** | Pascal/Delphi | Protocol decoder + simulator for military avionic bus |

---

## Python Automation

### Core Scripts

| Script | Purpose |
|---|---|
| `morning_brief.py` | Async daily brief: hh.kz + Habr Career vacancies, DB save, Telegram + Google Calendar |
| `session_prompt.py` | Interactive job search session guide with vacancy selection |
| `cover_letter.py` | AI cover letter generator via Anthropic Claude (templates A/B/C + `--top` mode) |
| `telegram_monitor.py` | Monitors C++/Qt/Embedded Telegram channels, filters duplicates via DB |
| `upwork_email_monitor.py` | Parses Gmail for Upwork job alerts, posts to Telegram |
| `batch_add_from_json.py` | Bulk vacancy import with retry + partial-write guard |
| `follow_up.py` | Detects stale applications (7d+), generates follow-up messages |
| `skill_gap_report.py` | Analyses vacancy requirements vs. profile, ranks skill gaps |
| `kpi_report.py` | Weekly KPI: applications, response rate, interviews, Connects spent |
| `sync_to_sheets.py` | PostgreSQL → Google Sheets mirror with charts and formatting |

### Exception Hierarchy (`exceptions.py`)

```
JobSearchError
├── ConfigError        # missing env var
├── DbConnectionError  # PostgreSQL unreachable
├── DbQueryError       # SQL error
├── ApiError           # external API failure
│   ├── HhApiError
│   ├── AnthropicApiError
│   └── TelegramApiError
├── SheetsError        # Google Sheets
└── IoError            # file operations
```

### `db.py` — Database Layer

- Custom exceptions: `DbConnectionError`, `DbQueryError`
- `health_check()` — DB ping, returns `""` if OK or error description
- `logging.getLogger(__name__)` — structured logging
- Context manager (`with Database() as db:`)
- Idempotent `connect()`, RAII-safe `__exit__`

---

## FastAPI REST API

**Live:** `https://web-production-f7596.up.railway.app`

| Endpoint | Description |
|---|---|
| `GET /health` | DB + Redis status |
| `GET/POST /vacancies` | List / add vacancies |
| `PATCH/DELETE /vacancies/{id}` | Update / delete |
| `GET/POST /freelance` | Freelance projects |
| `GET /stats` | Aggregate stats (Redis cached 5 min) |
| `POST /brief/run` | Trigger morning brief |
| `WS /ws/updates` | Real-time vacancy stream |

Auth: `Authorization: Bearer <API_TOKEN>` on write endpoints.

---

## Tests

```bash
pytest test_morning_brief.py         # 18 tests — async, mock aiohttp
pytest test_api.py                   # 25 tests — FastAPI TestClient, in-memory SQLite
pytest test_batch_add_from_json.py   # retry logic, partial-write guard
pytest test_cover_letter.py          # AI prompt building, template selection
pytest test_monitors.py              # Telegram + Upwork parsers
# + test_follow_up, test_freelance, test_report_and_add, test_skill_gap_report, test_hh_auth
```

---

## Quick Start

```bash
git clone https://github.com/stanislav-perfilyev/job-search-automation-portfolio.git
cd job-search-automation-portfolio
cp .env.example .env          # fill DATABASE_URL, API_TOKEN, TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY
pip install -r requirements.txt -r requirements_api.txt
python init_db.py
uvicorn app.main:app --reload --port 8000
# or: docker compose up --build
```

---

## Tech Stack

**Python:** asyncio · aiohttp · FastAPI · SQLAlchemy 2 (async) · psycopg2 · Pydantic v2 · APScheduler · anthropic · google-api-python-client

**C++/Qt:** C++17 · Qt6 · QtCharts · QAbstractTableModel · CMake · CTest · GoogleTest

**Infrastructure:** PostgreSQL (Neon) · Redis · Docker · Railway · GitHub Actions · Nginx
