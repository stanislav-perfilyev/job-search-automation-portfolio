# Qt Job Search Dashboard

[![Qt Dashboard CI](https://github.com/stanislav-perfilyev/job-search-automation/actions/workflows/qt_ci.yml/badge.svg)](https://github.com/stanislav-perfilyev/job-search-automation/actions/workflows/qt_ci.yml)

**Portfolio project #8** — Desktop application for tracking job search progress.  
Connects to a live PostgreSQL (Neon) database and can launch Python automation scripts directly from the UI.

## Stack

- **Qt 6.5+** · C++17
- **QtCharts** — 3 live charts (pie, bar, histogram)
- **QSqlTableModel** + custom `QAbstractTableModel`
- **QSortFilterProxyModel** — multi-field filter
- **QProcess** — run Python scripts with live stdout/stderr stream
- **PostgreSQL** (Neon cloud) via QPSQL driver
- **Dark QSS theme**
- **QtTest** unit tests · GitHub Actions CI

## Architecture

```
src/
├── main.cpp
├── mainwindow/      ← QMainWindow, menus (Файл/Вид/Инструменты), KPI bar
├── models/
│   ├── ivacancymodel.h       ← Abstract interface
│   ├── vacancysqlmodel.*     ← PostgreSQL model, setData() → UPDATE
│   └── vacancyfiltermodel.*  ← Text + status filter proxy
├── views/
│   ├── vacancyview.*         ← QTableView + search toolbar
│   └── statisticsview.*      ← 3× QChartView (status/monthly/salary)
├── widgets/
│   ├── kpiwidget.*           ← KPI card widget
│   ├── statusdelegate.*      ← Row coloring by status
│   └── processrunner.*       ← QProcess wrapper with live console output
├── dialogs/
│   ├── vacancydetaildialog.* ← Detail popup on double-click
│   ├── settingsdialog.*      ← DB connection config (QSettings)
│   └── scriptdialog.*        ← Python script launcher UI
└── utils/
    └── csvexporter.*         ← RFC 4180 CSV export with UTF-8 BOM
assets/style.qss              ← Dark Navy theme
tests/                        ← QtTest suite (SQLite in-memory)
.github/workflows/qt_ci.yml   ← Ubuntu CI: build + test
```

## Build

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
./build/JobSearchDashboard
```

Requires Qt6 with `Qt6::Sql` + QPSQL plugin.  
On Ubuntu: `sudo apt install libqt6sql6-psql`

## DB Setup

First launch: **Файл → Настройки**, enter Neon credentials:
- Host: `your-host.neon.tech`
- Database: `neondb` · User: `jobuser` · Port: `5432`

Credentials stored via `QSettings`.

## Features

| Feature | Detail |
|---|---|
| KPI bar | Total / Active / Interview / Conversion % |
| Vacancy table | Sort by any column, filter by text + status |
| Inline edit | Double-click title/status/notes → saves to DB |
| Detail dialog | Opens on row double-click, URL launch button |
| Statistics tab | Status pie · Monthly bar · Salary histogram |
| **CSV Export** | **Ctrl+E → save to file, UTF-8 BOM for Excel** |
| **Script launcher** | **Ctrl+R → run any Python script with live output** |
| Auto-refresh | Every 5 min; F5 for manual |
| Dark theme | Full QSS dark navy palette |

## Python Scripts (Инструменты menu)

The dashboard can launch scripts from the parent project directory:

| Script | Action |
|---|---|
| `sync_to_sheets.py` | Mirror PostgreSQL → Google Sheets |
| `skill_gap_report.py` | Analyze skill gaps from all vacancies |
| `report.py` | Print DB statistics |
| `cover_letter.py` | Generate cover letter |
| `kpi_report.py` | Weekly KPI report → Telegram |
| `morning_brief.py` | Morning briefing |
| `follow_up.py` | Follow-up on stale applications |

## Tests

```bash
cd build && ctest --output-on-failure
# Or headless:
QT_QPA_PLATFORM=offscreen ctest --output-on-failure
```

Tests use QtTest + in-memory SQLite — no Neon connection needed in CI.
