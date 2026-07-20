# Job Search Automation

Production-grade job search automation system built with **Python 3.11 + C++17/Qt6**.  
All code follows senior engineering standards: custom exceptions, structured logging, RAII, OOP interfaces, unit tests.

**Live API:** [`https://web-production-f7596.up.railway.app`](https://web-production-f7596.up.railway.app)

---

## Repository Structure

```
job-search-automation-portfolio/
├── portfolio/          ← C++ portfolio projects (Qt6, WinAPI, QML, D-Bus, Pascal)
├── app/                ← FastAPI REST + WebSocket backend (deployed on Railway)
├── automation/         ← Python automation scripts (bots, parsers, AI cover letters)
├── db/                 ← Database layer (PostgreSQL, custom exceptions, migrations)
├── tests/              ← Test suite (pytest, 100+ tests)
├── scripts/            ← Internal utilities and migration tools
└── .github/workflows/  ← 6 GitHub Actions bots running 24/7
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  automation/   (Python 3.11 asyncio)                                 │
│  morning_brief · telegram_monitor · upwork_monitor · cover_letter    │
├──────────────────────────────────────────────────────────────────────┤
│  app/   FastAPI REST + WebSocket                                      │
│  /vacancies  /freelance  /stats  /health  /brief/run  /ws/updates    │
│  Railway (prod) · PostgreSQL Neon · Redis cache · JWT auth           │
├──────────────────────────────────────────────────────────────────────┤
│  db/   Database layer                                                 │
│  PostgreSQL (Neon) · Google Sheets mirror · custom exception tree    │
├──────────────────────────────────────────────────────────────────────┤
│  portfolio/   C++ projects                                            │
│  Qt6 · WinAPI · QML · D-Bus · MIL-STD-1553 · GoogleTest / QTest     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## C++ Portfolio (`portfolio/`)

| Project | Tech | Highlights |
|---|---|---|
| **[Qt Job Dashboard](portfolio/qt-job-dashboard/)** | Qt6, C++17, SQLite/PostgreSQL, QtCharts | `QAbstractTableModel`, `QSortFilterProxyModel`, RAII, `Q_DISABLE_COPY_MOVE`, 18 QTest tests |
| **[WinAPI Showcase](portfolio/winapi_showcase/)** | C++17, WinAPI | ProcessMonitor, FileWatcher, Named Pipe IPC; RAII handles, 9 GoogleTest tests |
| **[QML System Monitor](portfolio/qml_system_monitor/)** | Qt6, QML, C++ backend | Live CPU/RAM/disk charts, abstract `ISystemStats`, `[[nodiscard]]`, 7 tests |
| **[D-Bus Service](portfolio/dbus_service/)** | C++17, Qt D-Bus | `SystemInfoService`, typed error signals, client + server, 5 tests |
| **[DAQ Bug Fix](https://github.com/stanislav-perfilyev/cpp-code-review)** | C++, multithreading | Fixed race condition in a production DAQ data collection system |
| **[MIL-STD-1553 Analyzer](portfolio/mil1553_analyzer/)** | Pascal/Delphi | Protocol decoder + simulator for military avionic bus |

---

## Python Automation (`automation/`)

| Script | What it does |
|---|---|
| `morning_brief.py` | Async daily digest: hh.kz + Habr Career + Telegram channels, saves to DB, sends via Telegram + reads Google Calendar |
| `telegram_monitor.py` | Monitors 3 C++/Qt/Embedded Telegram channels every 4 h, deduplicates via DB |
| `upwork_email_monitor.py` | Parses Gmail for Upwork job alerts, posts matching vacancies to Telegram |
| `cover_letter.py` | AI cover letter generator using Anthropic Claude — templates A/B/C + `--top` quality mode |
| `follow_up.py` | Detects stale applications (7 d+), generates personalised follow-up messages |
| `skill_gap_report.py` | Analyses vacancy requirements vs. profile, ranks top missing skills |
| `kpi_report.py` | Weekly KPI: applications sent, response rate, interviews, Connects spent |
| `sync_to_sheets.py` | PostgreSQL → Google Sheets mirror with charts and auto-formatting |
| `report.py` | Daily/weekly stats report via Telegram |
| `batch_add_from_json.py` | Bulk vacancy import with retry + partial-write guard |
| `add_vacancy.py` | Add a single vacancy to PostgreSQL |
| `freelance_add.py` / `freelance_report.py` | Freelance pipeline tracker (Upwork Connects, status, weekly report) |

---

## FastAPI Backend (`app/`)

**Live:** `https://web-production-f7596.up.railway.app`

| Endpoint | Description |
|---|---|
| `GET /health` | DB + Redis status |
| `GET /vacancies` | List vacancies with filtering |
| `POST /vacancies` | Add a vacancy |
| `PATCH /DELETE /vacancies/{id}` | Update / delete |
| `GET /freelance` | Freelance project list |
| `GET /stats` | Aggregate stats (Redis-cached 5 min) |
| `POST /brief/run` | Trigger morning brief |
| `WS /ws/updates` | Real-time vacancy stream |

Auth: `Authorization: Bearer <API_TOKEN>` on write endpoints.

---

## Database Layer (`db/`)

### Custom Exception Hierarchy

```
JobSearchError
├── ConfigError          # missing env var
├── DbConnectionError    # PostgreSQL unreachable
├── DbQueryError         # SQL error
├── ApiError             # external API failure
│   ├── HhApiError
│   ├── AnthropicApiError
│   └── TelegramApiError
├── SheetsError          # Google Sheets
└── IoError              # file operations
```

### `db.py` — Database Class

- Context manager (`with Database() as db:`) — RAII-safe
- `health_check()` — DB ping
- `logging.getLogger(__name__)` — structured logging
- Idempotent `connect()`, auto-close `__exit__`

---

## Tests (`tests/`)

```bash
pytest tests/test_morning_brief.py    # 18 tests — async, mock aiohttp
pytest tests/test_api.py              # 25 tests — FastAPI TestClient, in-memory SQLite
pytest tests/test_cover_letter.py     # AI prompt building, template selection
pytest tests/test_monitors.py         # Telegram + Upwork parsers
pytest tests/                         # run all 100+ tests
```

---

## GitHub Actions (`automation/` is the runtime target)

| Workflow | Schedule | What runs |
|---|---|---|
| `morning_brief.yml` | Daily 08:10 Almaty | `automation/morning_brief.py` |
| `telegram_monitor.yml` | Every 4 h | `automation/telegram_monitor.py` |
| `upwork_monitor.yml` | Every 30 min | `automation/upwork_email_monitor.py` |
| `daily_report.yml` | Daily 19:00 Almaty | `automation/report.py --mode check` |
| `weekly_report.yml` | Friday 17:00 Almaty | `automation/report.py --mode full` |
| `freelance_weekly.yml` | Sunday 13:00 Almaty | `automation/freelance_report.py --weekly` |

---

## Quick Start

```bash
git clone https://github.com/stanislav-perfilyev/job-search-automation-portfolio.git
cd job-search-automation-portfolio

cp .env.example .env          # fill DATABASE_URL, API_TOKEN, TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY
pip install -r requirements.txt -r requirements_api.txt

PYTHONPATH=. python db/init_db.py          # initialise PostgreSQL schema
uvicorn app.main:app --reload --port 8000  # start API
# or: docker compose up --build

PYTHONPATH=. python automation/morning_brief.py   # run the daily brief manually
PYTHONPATH=. pytest tests/                         # run all tests
```

---

## Tech Stack

**Python:** asyncio · aiohttp · FastAPI · SQLAlchemy 2 (async) · psycopg2 · Pydantic v2 · APScheduler · anthropic · google-api-python-client

**C++/Qt:** C++17 · Qt6 · QtCharts · QAbstractTableModel · CMake · CTest · GoogleTest · QTest

**Infrastructure:** PostgreSQL (Neon) · Redis · Docker · Railway · GitHub Actions
