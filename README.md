# Job Search Automation

A Python automation system for tracking a C++ developer job search — built with three REST APIs, CI/CD on GitHub Actions, and Telegram-based reporting.

## What it does

| Script | Trigger | What it does |
|---|---|---|
| `morning_brief.py` | GitHub Actions, 09:00 daily | Fetches new C++ vacancies from hh.kz API + Habr Career RSS + Google Sheets status, sends a Telegram summary |
| `telegram_monitor.py` | GitHub Actions, every 4 h | Scrapes 8 Telegram channels for C++ job posts, notifies via Telegram Bot |
| `report.py` | Manual | Builds an analytics chart (matplotlib) from Google Sheets data and sends it to Telegram |
| `add_vacancy.py` | Manual / via batch script | Appends a single application row to Google Sheets via Sheets API v4 |
| `batch_add_from_json.py` | Manual | Reads `session_vacancies.json` and adds all entries to Sheets in bulk |

## Architecture

```
GitHub Actions (cron)
    ├── morning_brief.py  ──► hh.kz RSS API
    │                    ──► Habr Career RSS
    │                    ──► Google Sheets API v4  (OAuth2 JWT, service account)
    │                    ──► Telegram Bot API       (sendMessage)
    │
    └── telegram_monitor.py ──► t.me/s/{channel}  (8 channels, keyword filter)
                              ──► Telegram Bot API  (sendMessage)

Local / manual
    ├── add_vacancy.py        ──► Google Sheets API v4
    ├── batch_add_from_json.py ─► add_vacancy.py × N
    └── report.py             ──► Google Sheets API v4
                              ──► matplotlib → PNG
                              ──► Telegram Bot API  (sendPhoto)
```

## Stack

- **Python 3.11** — no framework, stdlib + minimal deps
- **GitHub Actions** — cron CI/CD, secrets management
- **Google Sheets API v4** — JWT service account auth (works without `google-auth` lib via `cryptography`)
- **Telegram Bot API** — `sendMessage`, `sendPhoto`
- **hh.kz RSS** — vacancy feed, parsed with `re`
- **Habr Career RSS** — parsed with `re`
- **matplotlib** — dark-theme analytics charts sent as PNG to Telegram

## Setup

### 1. Clone and install

```bash
git clone https://github.com/stanislav-perfilyev/job-search-automation-portfolio.git
cd job-search-automation-portfolio
pip install -r requirements.txt
```

### 2. Create a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Copy the token
3. Get your chat ID from [@userinfobot](https://t.me/userinfobot)

### 3. Create a Google service account

1. [Google Cloud Console](https://console.cloud.google.com/) → Create project → Enable **Google Sheets API**
2. IAM → Service Accounts → Create → Download JSON key → save as `sheets_key.json` (see `sheets_key.json.example`)
3. Share your spreadsheet with the service account email (Editor role)

### 4. Configure environment

```bash
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SPREADSHEET_ID
```

For local use, source `.env` before running:
```bash
export $(cat .env | xargs)
python morning_brief.py
```

### 5. Deploy to GitHub Actions

Add these repository secrets (Settings → Secrets → Actions):

| Secret | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `SPREADSHEET_ID` | Google Sheets ID from the URL |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `cat sheets_key.json \| base64 -w 0` |

The workflows run automatically on schedule. Trigger manually from the Actions tab.

## Google Sheets schema

The sheet named `Вакансии` expects columns A–K:

| A | B | C | D | E | F | G | H | I | J | K |
|---|---|---|---|---|---|---|---|---|---|---|
| Vacancy | Company | URL | Source | Template | Date (hh) | Date (corp) | Date (social) | Status | Comment | HR contact |

## Usage

```bash
# Add a vacancy manually
python add_vacancy.py \
  --vacancy "C++ Developer" \
  --company "Acme Corp" \
  --url "https://hh.kz/vacancy/123" \
  --source "hh.kz" \
  --template "B"

# Add multiple vacancies from JSON (fill session_vacancies.json during session)
python batch_add_from_json.py session_vacancies.json

# Send a session report
python report.py --mode full    # after a search session
python report.py --mode check   # after a notification check
```

## Security

All secrets are passed via environment variables. `sheets_key.json` and `.env` are in `.gitignore` and must never be committed. GitHub Actions uses repository secrets — the raw values are never visible in logs.
