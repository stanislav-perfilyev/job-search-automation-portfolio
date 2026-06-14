#!/usr/bin/env python3
"""
Morning job-search briefing bot.

Sends a Telegram summary every morning:
  - Stale applications (no reply in N days) from Google Sheets
  - New C++ vacancies from hh.kz RSS (last 24 h)
  - New C++ vacancies from Habr Career RSS (last 24 h)
  - New posts from Telegram channels (last 12 h)

Usage:
  python morning_brief.py

Required env vars (see .env.example):
  TELEGRAM_BOT_TOKEN        — Telegram Bot API token
  TELEGRAM_CHAT_ID          — Target chat/user ID
  GOOGLE_SERVICE_ACCOUNT_JSON — base64-encoded service account JSON (GitHub Actions)
  SPREADSHEET_ID            — Google Sheets spreadsheet ID

Local dev: put sheets_key.json next to this script (see sheets_key.json.example).
"""

import sys
import re
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime

import os
import base64
import tempfile

# ── Config (from environment) ──────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "")
SHEET_NAME     = "Вакансии"
SCOPES         = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

TG_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

if not TG_BOT_TOKEN or not TG_CHAT_ID:
    sys.exit("ERROR: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set.")
if not SPREADSHEET_ID:
    sys.exit("ERROR: SPREADSHEET_ID must be set.")

def _get_key_file() -> Path:
    """Returns path to service account JSON.
    Priority: GOOGLE_SERVICE_ACCOUNT_JSON env (base64) → sheets_key.json next to script."""
    env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        try:
            decoded = base64.b64decode(env_json)
        except Exception:
            decoded = env_json.encode()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="wb")
        tmp.write(decoded)
        tmp.close()
        return Path(tmp.name)
    key_path = Path(__file__).parent / "sheets_key.json"
    if not key_path.exists():
        sys.exit("ERROR: sheets_key.json not found. See sheets_key.json.example.")
    return key_path

KEY_FILE = _get_key_file()

ALMATY_TZ      = timezone(timedelta(hours=5))
STALE_DAYS     = 5
HH_MAX_AGE_H   = 24
TG_MAX_AGE_H   = 12
HABR_MAX_AGE_H = 24
HABR_RSS_URL   = "https://career.habr.com/vacancies/rss?q=C%2B%2B&sort=date"

TG_CHANNELS = [
    'cppdevjob', 'c_rabota', 'forcpp', 'runello_rus_c20',
    'workitkz', 'it_vakansii_jobs', 'devs_it', 'jc_it'
]
TG_KEYWORDS = [
    'c++', 'c/c++', 'qt', 'embedded', 'firmware',
    'микроконтроллер', 'stm32', 'esp32', 'rtos',
    'c developer', 'c++ developer', 'c/c++ developer'
]

# ── Google Sheets auth (service account, no extra libs needed) ─────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def _get_sheets_token() -> str:
    """JWT-based service account auth — no google-auth library required."""
    import time, json as _json
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        USE_CRYPTO = True
    except ImportError:
        USE_CRYPTO = False

    key_data = json.loads(KEY_FILE.read_text())
    sa_email = key_data["client_email"]
    private_key_pem = key_data["private_key"]

    now = int(time.time())
    header  = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "iss": sa_email,
        "scope": " ".join(SCOPES),
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": now + 3600,
    }).encode())
    signing_input = f"{header}.{payload}".encode()

    if USE_CRYPTO:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        private_key = load_pem_private_key(private_key_pem.encode(), password=None)
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    else:
        import subprocess
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pem', mode='w') as f:
            f.write(private_key_pem)
            tmp_key = f.name
        try:
            proc = subprocess.run(
                ['openssl', 'dgst', '-sha256', '-sign', tmp_key],
                input=signing_input, capture_output=True
            )
            signature = proc.stdout
        finally:
            os.unlink(tmp_key)

    jwt_token = f"{header}.{payload}.{_b64url(signature)}"
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token,
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())["access_token"]

def _get_sheets_token_via_lib() -> str:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GRequest
    creds = service_account.Credentials.from_service_account_file(
        str(KEY_FILE), scopes=SCOPES
    )
    creds.refresh(GRequest())
    return creds.token

def get_sheets_token() -> str:
    try:
        return _get_sheets_token_via_lib()
    except Exception:
        return _get_sheets_token()

# ── Read Google Sheets ──────────────────────────────────────────────────────
def read_vacancies() -> dict:
    token = get_sheets_token()
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
        f"/values/{urllib.parse.quote(SHEET_NAME)}!A:K"
    )
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    rows = resp.get("values", [])
    data_rows = rows[1:] if len(rows) > 1 else []
    today = datetime.now(ALMATY_TZ).date()

    total = len(data_rows)
    waiting = stale = interview = offer = rejected = 0
    stale_list = []

    for row in data_rows:
        while len(row) < 11:
            row.append("")
        vacancy = row[0]
        company = row[1]
        status  = row[8].lower().strip() if row[8] else "ожидание"
        date_str = next((row[i].strip() for i in [5, 6, 7] if row[i]), "")

        if "интервью" in status or "собес" in status:
            interview += 1
        elif "оффер" in status:
            offer += 1
        elif "отказ" in status:
            rejected += 1
        else:
            waiting += 1
            if date_str:
                try:
                    d = datetime.strptime(date_str, "%d.%m.%Y").date()
                    age = (today - d).days
                    if age >= STALE_DAYS:
                        stale += 1
                        stale_list.append(f"{vacancy} / {company} ({age}д)")
                except ValueError:
                    pass

    return {
        "total": total, "waiting": waiting, "stale": stale,
        "stale_list": stale_list, "interview": interview,
        "offer": offer, "rejected": rejected,
    }

# ── hh.kz RSS ───────────────────────────────────────────────────────────────
def fetch_hh_rss() -> list:
    urls = [
        "https://hh.kz/search/vacancy/rss?text=C%2B%2B+developer&area=160&experience=noExperience&experience=between1And3",
        "https://hh.kz/search/vacancy/rss?text=C%2B%2B&area=160&salary=300000&currency=KZT",
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HH_MAX_AGE_H)
    seen, results = set(), []

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[hh.kz] RSS error: {e}", file=sys.stderr)
            continue

        for item in re.findall(r'<item>([\s\S]*?)</item>', xml):
            title_m   = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item) or re.search(r'<title>(.*?)</title>', item)
            link_m    = re.search(r'<link>(.*?)</link>', item)
            pubdate_m = re.search(r'<pubDate>(.*?)</pubDate>', item)
            salary_m  = re.search(r'<hh:salary>([\s\S]*?)</hh:salary>', item)
            if not (title_m and link_m):
                continue
            title  = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
            link   = link_m.group(1).strip()
            salary = re.sub(r'<[^>]+>', '', salary_m.group(1)).strip() if salary_m else ""
            if link in seen:
                continue
            seen.add(link)
            if pubdate_m:
                try:
                    pub_dt = parsedate_to_datetime(pubdate_m.group(1))
                    if pub_dt.tzinfo is None:
                        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                except Exception:
                    pass
            results.append({"title": title, "link": link, "salary": salary})

    return results

# ── Habr Career RSS ──────────────────────────────────────────────────────────
def fetch_habr_rss() -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HABR_MAX_AGE_H)
    seen, results = set(), []
    try:
        req = urllib.request.Request(HABR_RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
        xml = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[Habr] RSS error: {e}", file=sys.stderr)
        return []

    for item in re.findall(r'<item>([\s\S]*?)</item>', xml):
        title_m   = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item) or re.search(r'<title>(.*?)</title>', item)
        link_m    = re.search(r'<link>(.*?)</link>', item)
        author_m  = re.search(r'<author>(.*?)</author>', item)
        pubdate_m = re.search(r'<pubDate>(.*?)</pubDate>', item)
        if not (title_m and link_m):
            continue
        title   = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        link    = link_m.group(1).strip()
        company = re.sub(r'<[^>]+>', '', author_m.group(1)).strip() if author_m else ""
        if link in seen:
            continue
        seen.add(link)
        if pubdate_m:
            try:
                pub_dt = parsedate_to_datetime(pubdate_m.group(1))
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
            except Exception:
                pass
        results.append({"title": title, "link": link, "company": company})

    return results

# ── Telegram channels ───────────────────────────────────────────────────────
def fetch_tg_vacancies() -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=TG_MAX_AGE_H)
    seen, results = set(), []

    for channel in TG_CHANNELS:
        try:
            req = urllib.request.Request(
                f"https://t.me/s/{channel}", headers={"User-Agent": "Mozilla/5.0"}
            )
            html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[TG] Error {channel}: {e}", file=sys.stderr)
            continue

        block_re = re.compile(
            r'data-post="([^"]+)"[\s\S]*?datetime="([^"]+)"[\s\S]*?'
            r'class="tgme_widget_message_text[^"]*"[^>]*>([\s\S]*?)</div>\s*</div>'
        )
        for m in block_re.finditer(html):
            post_id, date_str, raw_html = m.group(1), m.group(2), m.group(3)
            if post_id in seen:
                continue
            seen.add(post_id)
            try:
                pub_dt = datetime.fromisoformat(date_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
            except Exception:
                continue
            text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', raw_html)).strip()
            if not any(kw in text.lower() for kw in TG_KEYWORDS):
                continue
            results.append({"channel": channel, "link": f"https://t.me/{post_id}", "title": text[:150]})

    return results

# ── Telegram send ────────────────────────────────────────────────────────────
def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send_telegram(text: str):
    url  = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    body = json.dumps({
        "chat_id": TG_CHAT_ID, "text": text,
        "parse_mode": "HTML", "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
    if not resp.get("ok"):
        raise RuntimeError(f"Telegram error: {resp}")

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    now_almaty = datetime.now(ALMATY_TZ)
    date_str   = now_almaty.strftime("%d.%m.%Y")
    time_str   = now_almaty.strftime("%H:%M")
    print(f"[{time_str}] Collecting morning brief data...")

    sheets_ok, stats = True, {}
    try:
        print("  📊 Reading Google Sheets...")
        stats = read_vacancies()
        print(f"     Total: {stats['total']}, waiting: {stats['waiting']}, stale: {stats['stale']}")
    except Exception as e:
        print(f"  ⚠️  Sheets unavailable: {e}", file=sys.stderr)
        sheets_ok = False

    print("  🔍 Fetching hh.kz RSS...")
    hh_vacancies = fetch_hh_rss()
    print(f"     Found: {len(hh_vacancies)}")

    print("  📰 Fetching Habr Career RSS...")
    habr_vacancies = fetch_habr_rss()
    print(f"     Found: {len(habr_vacancies)}")

    print("  📢 Scraping Telegram channels...")
    tg_vacancies = fetch_tg_vacancies()
    print(f"     Found: {len(tg_vacancies)}")

    lines = [f"☀️ <b>Good morning! Summary for {date_str}</b>\n"]

    if sheets_ok and stats:
        lines.append("📋 <b>APPLICATIONS:</b>")
        lines.append(f"• Total: {stats['total']}")
        lines.append(f"• Waiting: {stats['waiting']}")
        if stats['interview']:
            lines.append(f"• 🎯 Interviews: {stats['interview']}")
        if stats['offer']:
            lines.append(f"• 🏆 Offers: {stats['offer']}")
        if stats['stale']:
            lines.append(f"• ⏰ Stale >{STALE_DAYS}d: {stats['stale']}")
            for s in stats['stale_list']:
                lines.append(f"  — {_esc(str(s))}")
        lines.append("")
    else:
        lines.append("📋 <b>APPLICATIONS:</b> <i>(sheet unavailable)</i>\n")

    if hh_vacancies:
        lines.append(f"🔍 <b>HH.KZ — new in {HH_MAX_AGE_H}h: {len(hh_vacancies)}</b>")
        for v in hh_vacancies:
            sal = f" · {_esc(v['salary'])}" if v.get('salary') else ""
            lines.append(f"📌 {_esc(v['title'][:80])}{sal}")
            lines.append(f"🔗 {v['link']}")
        lines.append("")
    else:
        lines.append(f"🔍 <b>HH.KZ:</b> <i>(no new in {HH_MAX_AGE_H}h)</i>\n")

    if habr_vacancies:
        lines.append(f"📰 <b>HABR CAREER — new in {HABR_MAX_AGE_H}h: {len(habr_vacancies)}</b>")
        for v in habr_vacancies:
            co = f" · {_esc(v['company'])}" if v.get('company') else ""
            lines.append(f"📌 {_esc(v['title'][:80])}{co}")
            lines.append(f"🔗 {v['link']}")
        lines.append("")
    else:
        lines.append(f"📰 <b>HABR CAREER:</b> <i>(no new in {HABR_MAX_AGE_H}h)</i>\n")

    if tg_vacancies:
        lines.append(f"📢 <b>TELEGRAM — new in {TG_MAX_AGE_H}h: {len(tg_vacancies)}</b>")
        for v in tg_vacancies:
            lines.append(f"📌 {_esc(v['title'][:100])}")
            lines.append(f"🔗 {v['link']}  @{_esc(v['channel'])}")
        lines.append("")
    else:
        lines.append(f"📢 <b>TELEGRAM:</b> <i>(no new in {TG_MAX_AGE_H}h)</i>\n")

    total_new = len(hh_vacancies) + len(habr_vacancies) + len(tg_vacancies)
    lines.append(f"<i>Total new vacancies: {total_new}</i>")

    message = "\n".join(lines)
    MAX_LEN = 4000

    if len(message) <= MAX_LEN:
        print(f"\nSending to Telegram ({len(message)} chars)...")
        send_telegram(message)
    else:
        parts, current, current_len = [], [], 0
        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > MAX_LEN and current:
                parts.append("\n".join(current))
                current, current_len = [line], line_len
            else:
                current.append(line)
                current_len += line_len
        if current:
            parts.append("\n".join(current))
        print(f"\nLong message ({len(message)} chars), splitting into {len(parts)} parts...")
        for i, part in enumerate(parts, 1):
            print(f"  Sending part {i}/{len(parts)} ({len(part)} chars)...")
            send_telegram(part)

    print("✅ Done!")


if __name__ == "__main__":
    main()
