#!/usr/bin/env python3
"""
Утренний брифинг по поиску работы — ASYNC v2.

asyncio + aiohttp, параллельные запросы ко всем источникам.
Изменения v2:
  - Фикс: asyncio.coroutine → нормальные async-функции (совместимо с Python 3.11+)
  - Фикс: return_exceptions=True в gather + обработка каждого результата
  - Фикс: лимит вакансий MAX_PER_SOURCE (иначе 181 hh.kz → 19к симв., 5 частей)
  - Retry с экспоненциальным backoff (transient DNS/timeout ошибки)
  - TCPConnector(limit=20) — не перегружаем серверы
  - Telegram 429 retry при multi-part отправке
  - Timing footer: [asyncio] Выполнено за X.XX сек, источников: N

Запуск: python morning_brief.py
"""

import asyncio
import aiohttp
import time
import sys
import re
import json
import os
import base64
import tempfile
import html as _html_module
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

# ── PostgreSQL (опционально — если DATABASE_URL задан) ──────────────────
import logging as _logging
_DB_LOG = Path(__file__).parent / "db.log"
_db_log = _logging.getLogger("morning_brief.db")
if not _db_log.handlers:
    _db_log.setLevel(_logging.INFO)
    _db_log.addHandler(_logging.FileHandler(_DB_LOG, encoding="utf-8"))

def _save_vacancies_to_db(vacancies: list, source: str) -> int:
    """Сохраняет список вакансий в PostgreSQL. Возвращает кол-во вставленных."""
    import os
    if not os.environ.get("DATABASE_URL"):
        return 0
    try:
        from db import Database
        from datetime import date as _date
        saved = 0
        with Database() as db:
            for v in vacancies:
                url = v.get("link", "").strip()
                title = v.get("title", "").strip()
                if not url or not title:
                    continue
                try:
                    db.add_vacancy({
                        "date":    _date.today(),
                        "title":   title,
                        "company": v.get("company", ""),
                        "url":     url,
                        "source":  source,
                        "status":  "new",
                    })
                    saved += 1
                except Exception as _e:
                    _db_log.warning(f"skip {url}: {_e}")
        _db_log.info(f"morning_brief | {source}: {saved}/{len(vacancies)} saved to DB")
        return saved
    except Exception as e:
        _db_log.error(f"morning_brief DB error ({source}): {e}")
        return 0

# ── Константы ──────────────────────────────────────────────────────────────
SPREADSHEET_ID  = os.environ.get("SPREADSHEET_ID", "1ri78JxboQ477L7nLOmXJupe2ALORwKqbh-jiKuAL8XE")
SHEET_NAME      = "Вакансии"
SCOPES          = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

TG_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "")

MAX_PER_SOURCE  = 15   # макс. вакансий из hh.kz и Habr в сообщении (иначе 181 вак. = 19к симв.)
MAX_TG_POSTS    = 10   # макс. постов из Telegram-каналов
MAX_MSG_LEN     = 4000 # лимит Telegram

def _get_key_file() -> Path:
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
    return Path(__file__).parent / "sheets_key.json"

KEY_FILE = _get_key_file()

ALMATY_TZ       = timezone(timedelta(hours=5))
STALE_DAYS      = 5
STALE_REMINDED_FILE = Path(__file__).parent / "stale_reminded.json"
HH_MAX_AGE_H    = 24
HABR_MAX_AGE_H  = 24
TG_MAX_AGE_H    = 168

HH_RSS_URLS = [
    "https://hh.kz/search/vacancy/rss?text=C%2B%2B+developer&area=160&experience=noExperience&experience=between1And3",
    "https://hh.kz/search/vacancy/rss?text=C%2B%2B&area=160&salary=300000&currency=KZT",
    "https://hh.kz/search/vacancy/rss?text=Qt+%D1%80%D0%B0%D0%B7%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%87%D0%B8%D0%BA&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=embedded+developer&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=firmware+developer&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=%D1%81%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%BD%D1%8B%D0%B9+%D0%BF%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%B8%D1%81%D1%82&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=Python+%D1%80%D0%B0%D0%B7%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%87%D0%B8%D0%BA&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=Python+developer&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=Python+backend&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=%D0%B0%D0%B2%D1%82%D0%BE%D0%BC%D0%B0%D1%82%D0%B8%D0%B7%D0%B0%D1%86%D0%B8%D1%8F+%D1%80%D0%B0%D0%B7%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%87%D0%B8%D0%BA&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=automation+engineer&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=telegram+bot+%D1%80%D0%B0%D0%B7%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%87%D0%B8%D0%BA&schedule=remote",
    "https://hh.kz/search/vacancy/rss?text=%D0%BF%D0%B0%D1%80%D1%81%D0%B8%D0%BD%D0%B3+%D1%80%D0%B0%D0%B7%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%87%D0%B8%D0%BA&schedule=remote",
]

HABR_RSS_URLS = [
    "https://career.habr.com/vacancies/rss?q=C%2B%2B&sort=date",
    "https://career.habr.com/vacancies/rss?q=Qt&sort=date",
    "https://career.habr.com/vacancies/rss?q=embedded+%D1%83%D0%B4%D0%B0%D0%BB%D1%91%D0%BD%D0%BD%D0%BE&sort=date",
    "https://career.habr.com/vacancies/rss?q=%D1%81%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%BD%D1%8B%D0%B9+%D0%BF%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%B8%D1%81%D1%82&sort=date",
    "https://career.habr.com/vacancies/rss?q=Python+%D1%80%D0%B0%D0%B7%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%87%D0%B8%D0%BA&sort=date",
    "https://career.habr.com/vacancies/rss?q=Python+developer&sort=date",
    "https://career.habr.com/vacancies/rss?q=Python+backend&sort=date",
    "https://career.habr.com/vacancies/rss?q=%D0%B0%D0%B2%D1%82%D0%BE%D0%BC%D0%B0%D1%82%D0%B8%D0%B7%D0%B0%D1%86%D0%B8%D1%8F+%D1%80%D0%B0%D0%B7%D1%80%D0%B0%D0%B1%D0%BE%D1%82%D1%87%D0%B8%D0%BA&sort=date",
]

TG_CHANNELS = [
    "cppdevjob", "c_rabota", "forcpp", "runello_rus_c20",
    "workitkz", "it_vakansii_jobs", "devs_it", "jc_it",
    "python_jobs_ru", "pythonist_job", "automation_jobs_ru",
]

TG_KEYWORDS = [
    "c++", "c/c++", "qt", "embedded", "firmware",
    "микроконтроллер", "stm32", "esp32", "rtos",
    "разработчик c", "developer c", "c++ developer", "c/c++ developer",
    "с++", "с/с++", "разработчик с",
    "python developer", "python разработчик",
    "python backend", "fastapi", "django developer",
    "автоматизация разработчик", "automation engineer",
    "telegram bot", "телеграм бот", "бот разработчик",
    "парсинг", "скрапинг", "web scraping", "parsing developer",
    "linux developer", "bash developer", "devops python",
    "script developer", "скриптинг",
]

CLAUDEDEV_CHANNEL = "claudedevolper"
CLAUDEDEV_MAX_AGE_DAYS = 7
CLAUDEDEV_USEFUL_KEYWORDS = [
    "плагин", "plugin", "инструмент", "tool",
    "фриланс", "freelance", "заказ",
    "промпт", "prompt", "лайфхак",
    "claude code", "cursor", "agent",
    "парсер", "бот", "автоматизация",
    "скорость", "результат", "клиент",
]
CLAUDEDEV_SKIP_KEYWORDS = [
    "торговый бот", "криптовалют", "трейд", "binance",
    "курс за", "курс по", "обучение за",
]


# ── Google Auth (sync — выполняется ДО asyncio loop) ────────────────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _get_sheets_token_via_lib(scopes) -> str:
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request as GRequest
    creds = service_account.Credentials.from_service_account_file(str(KEY_FILE), scopes=scopes)
    creds.refresh(GRequest())
    return creds.token

def _get_sheets_token_raw(scopes) -> str:
    import time as _time
    key_data = json.loads(KEY_FILE.read_text())
    sa_email = key_data["client_email"]
    private_key_pem = key_data["private_key"]
    now = int(_time.time())
    header  = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "iss": sa_email, "scope": " ".join(scopes),
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now, "exp": now + 3600,
    }).encode())
    signing_input = f"{header}.{payload}".encode()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    pk = load_pem_private_key(private_key_pem.encode(), password=None)
    sig = pk.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    jwt_token = f"{header}.{payload}.{_b64url(sig)}"
    import urllib.request as _ureq, urllib.parse as _uparse
    data = _uparse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token,
    }).encode()
    req = _ureq.Request(
        "https://oauth2.googleapis.com/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    return json.loads(_ureq.urlopen(req, timeout=15).read())["access_token"]

def get_sheets_token() -> str:
    try:
        return _get_sheets_token_via_lib(SCOPES)
    except Exception:
        return _get_sheets_token_raw(SCOPES)

def get_calendar_token() -> str:
    try:
        return _get_sheets_token_via_lib(CALENDAR_SCOPES)
    except Exception:
        return _get_sheets_token_raw(CALENDAR_SCOPES)


# ── Async HTTP helper с retry ────────────────────────────────────────────────
_TIMEOUT = aiohttp.ClientTimeout(total=8)
_UA = "Mozilla/5.0 (compatible; JobBot/1.0)"
_MAX_RETRIES = 2        # 1 попытка + 2 повтора = итого 3 попытки
_RETRY_DELAY = 0.5      # сек между попытками (× 2 на каждой итерации)

async def _fetch(session: aiohttp.ClientSession, url: str,
                 headers: dict | None = None, auth_token: str | None = None) -> str | None:
    """Fetch URL: 8-сек таймаут, retry ×2 с backoff, None при ошибке (graceful fallback)."""
    h = {"User-Agent": _UA}
    if headers:
        h.update(headers)
    if auth_token:
        h["Authorization"] = f"Bearer {auth_token}"

    delay = _RETRY_DELAY
    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with session.get(url, timeout=_TIMEOUT, headers=h) as r:
                if r.status == 429:
                    # Rate limit — ждём и повторяем
                    retry_after = float(r.headers.get("Retry-After", delay * 2))
                    await asyncio.sleep(min(retry_after, 10))
                    continue
                r.raise_for_status()
                return await r.text(errors="replace")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                print(f"  ⚠️  [{url[:55]}…] {type(e).__name__} (попыток: {attempt+1})", file=sys.stderr)
    return None


# ── Парсеры (чистые функции, без IO) ────────────────────────────────────────
def _parse_hh_items(xml: str, cutoff: datetime, seen: set) -> list:
    results = []
    for item in re.findall(r"<item>([\s\S]*?)</item>", xml):
        title_m   = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item) \
                    or re.search(r"<title>(.*?)</title>", item)
        link_m    = re.search(r"<link>(.*?)</link>", item)
        pubdate_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
        salary_m  = re.search(r"<hh:salary>([\s\S]*?)</hh:salary>", item)
        if not (title_m and link_m):
            continue
        title  = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        link   = link_m.group(1).strip()
        salary = re.sub(r"<[^>]+>", "", salary_m.group(1)).strip() if salary_m else ""
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

def _parse_habr_items(xml: str, cutoff: datetime, seen: set) -> list:
    results = []
    for item in re.findall(r"<item>([\s\S]*?)</item>", xml):
        title_m   = re.search(r"<title><!\[CDATA\[(.*?)\]\]></title>", item) \
                    or re.search(r"<title>(.*?)</title>", item)
        link_m    = re.search(r"<link>(.*?)</link>", item)
        author_m  = re.search(r"<author>(.*?)</author>", item)
        pubdate_m = re.search(r"<pubDate>(.*?)</pubDate>", item)
        if not (title_m and link_m):
            continue
        title   = re.sub(r"<[^>]+>", "", title_m.group(1)).strip()
        link    = link_m.group(1).strip()
        company = re.sub(r"<[^>]+>", "", author_m.group(1)).strip() if author_m else ""
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

def _strip_tags(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html_module.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()

_TG_BLOCK_RE = re.compile(
    r'data-post="([^"]+)"'
    r"[\s\S]*?"
    r'datetime="([^"]+)"'
    r"[\s\S]*?"
    r'class="tgme_widget_message_text[^"]*"[^>]*>'
    r"([\s\S]*?)"
    r"</div>\s*</div>",
    re.MULTILINE,
)

def _parse_tg_page(page: str, channel: str, cutoff: datetime, now: datetime,
                   seen: set, seen_texts: set) -> list:
    results = []
    for m in _TG_BLOCK_RE.finditer(page):
        post_id, date_str, raw_html = m.group(1), m.group(2), m.group(3)
        if post_id in seen:
            continue
        seen.add(post_id)
        try:
            post_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if post_time < cutoff or post_time > now:
            continue
        text = _strip_tags(raw_html)
        if not any(kw in text.lower() for kw in TG_KEYWORDS):
            continue
        fp = text[:80].strip()
        if fp in seen_texts:
            continue
        seen_texts.add(fp)
        results.append({
            "channel": channel, "post_id": post_id,
            "text": text, "link": f"https://t.me/{post_id}", "date": date_str,
        })
    return results


# ── Async fetchers ────────────────────────────────────────────────────────────
async def read_vacancies_async(*_) -> dict:
    """Читает статистику вакансий из PostgreSQL (не Sheets)."""
    loop = asyncio.get_event_loop()
    try:
        from db import Database
        def _pg_call():
            with Database() as db:
                return db.get_vacancy_summary(stale_days=STALE_DAYS)
        result = await loop.run_in_executor(None, _pg_call)
        print(f"  [PG] Статистика: {result.get('total',0)} вакансий, "
              f"{result.get('waiting',0)} ожидают, {result.get('stale',0)} устаревших")
        return result
    except Exception as e:
        print(f"  [PG] Ошибка чтения статистики: {e}", file=__import__("sys").stderr)
        return {}


async def fetch_calendar_async(session: aiohttp.ClientSession, token: str) -> list:
    today = datetime.now(ALMATY_TZ)
    time_min = today.replace(hour=0, minute=0, second=0, microsecond=0)
    time_max = today.replace(hour=23, minute=59, second=59, microsecond=0)
    def to_rfc3339(dt):
        s = dt.strftime("%Y-%m-%dT%H:%M:%S%z")
        return s[:-2] + ":" + s[-2:]
    params = urllib.parse.urlencode({
        "timeMin": to_rfc3339(time_min), "timeMax": to_rfc3339(time_max),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": "20",
    })
    cal_id = urllib.parse.quote("stasperfiliyev@gmail.com")
    url = f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events?{params}"
    xml = await _fetch(session, url, auth_token=token)
    if xml is None:
        return []
    events = []
    for item in json.loads(xml).get("items", []):
        summary  = item.get("summary", "(без названия)")
        start    = item.get("start", {})
        start_dt = start.get("dateTime") or start.get("date", "")
        if "T" in start_dt:
            try:
                dt = datetime.fromisoformat(start_dt)
                time_label = dt.astimezone(ALMATY_TZ).strftime("%H:%M")
            except Exception:
                time_label = start_dt[:16]
        else:
            time_label = "весь день"
        events.append({"summary": summary, "time": time_label})
    return events


async def fetch_hh_rss_async(session: aiohttp.ClientSession) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HH_MAX_AGE_H)
    pages  = await asyncio.gather(*[_fetch(session, url) for url in HH_RSS_URLS],
                                  return_exceptions=True)
    seen, results = set(), []
    for xml in pages:
        if isinstance(xml, str):
            results.extend(_parse_hh_items(xml, cutoff, seen))
    return results[:MAX_PER_SOURCE]  # лимит вывода


async def fetch_habr_rss_async(session: aiohttp.ClientSession) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HABR_MAX_AGE_H)
    pages  = await asyncio.gather(*[_fetch(session, url) for url in HABR_RSS_URLS],
                                  return_exceptions=True)
    seen, results = set(), []
    for xml in pages:
        if isinstance(xml, str):
            results.extend(_parse_habr_items(xml, cutoff, seen))
    return results[:MAX_PER_SOURCE]


async def fetch_tg_vacancies_async(session: aiohttp.ClientSession) -> list:
    now    = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(hours=TG_MAX_AGE_H)
    pages  = await asyncio.gather(
        *[_fetch(session, f"https://t.me/s/{ch}") for ch in TG_CHANNELS],
        return_exceptions=True,
    )
    seen, seen_texts, results = set(), set(), []
    for channel, page in zip(TG_CHANNELS, pages):
        if isinstance(page, str):
            found = _parse_tg_page(page, channel, cutoff, now, seen, seen_texts)
            print(f"  📢 @{channel}: {len(found)} вак.")
            results.extend(found)
        else:
            err = page if isinstance(page, Exception) else "пропущен"
            print(f"  📢 @{channel}: пропущен ({type(err).__name__ if isinstance(err, Exception) else err})")
    return results[:MAX_TG_POSTS]


async def fetch_claudedev_async(session: aiohttp.ClientSession) -> list:
    now    = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(days=CLAUDEDEV_MAX_AGE_DAYS)
    page   = await _fetch(session, f"https://t.me/s/{CLAUDEDEV_CHANNEL}")
    if not isinstance(page, str):
        return []
    results = []
    for m in _TG_BLOCK_RE.finditer(page):
        post_id, date_str, raw_html = m.group(1), m.group(2), m.group(3)
        try:
            post_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        if post_time < cutoff or post_time > now:
            continue
        text = _strip_tags(raw_html)
        text_lower = text.lower()
        if any(kw in text_lower for kw in CLAUDEDEV_SKIP_KEYWORDS):
            continue
        if not any(kw in text_lower for kw in CLAUDEDEV_USEFUL_KEYWORDS):
            continue
        results.append({"post_id": post_id, "text": text[:300],
                         "link": f"https://t.me/{post_id}", "date": date_str})
    return results[:5]


async def send_telegram_async(session: aiohttp.ClientSession, text: str):
    """Отправка с retry при 429 Too Many Requests."""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        raise RuntimeError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы")
    url  = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    body = {"chat_id": TG_CHAT_ID, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True}
    for attempt in range(3):
        async with session.post(url, json=body,
                                timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 429:
                retry_after = float(r.headers.get("Retry-After", 5))
                print(f"  ⚠️  Telegram 429, жду {retry_after:.0f}с...")
                await asyncio.sleep(retry_after)
                continue
            resp = await r.json()
            if not resp.get("ok"):
                raise RuntimeError(f"Telegram error: {resp}")
            return
    raise RuntimeError("Telegram: превышено число попыток отправки")


# ── Follow-up (sync, файловый IO) ─────────────────────────────────────────
def get_stale_followup(stats: dict) -> list:
    now_local = datetime.now(ALMATY_TZ)
    if not (now_local.weekday() == 0 and now_local.isocalendar()[1] % 2 == 0):
        return []
    reminded = set()
    if STALE_REMINDED_FILE.exists():
        try:
            reminded = set(json.loads(STALE_REMINDED_FILE.read_text()))
        except Exception:
            pass
    new_stale = [item for item in stats.get("stale_list", []) if item not in reminded]
    if new_stale:
        reminded.update(new_stale)
        STALE_REMINDED_FILE.write_text(json.dumps(list(reminded), ensure_ascii=False))
    return new_stale


# ── Форматирование ───────────────────────────────────────────────────────────
def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _build_message(date_str, stats, calendar_events, hh_vacancies,
                   habr_vacancies, tg_vacancies, claudedev_posts,
                   is_monday, elapsed, n_sources,
                   hh_total, habr_total, tg_total) -> str:
    lines = [
        f"🤖 <b>Morning Brief</b> · <code>morning_brief.py</code>\n",
        f"☀️ <b>Доброе утро! Сводка на {date_str}</b>\n",
    ]
    if stats:
        lines.append("📋 <b>ОТКЛИКИ:</b>")
        lines.append(f"• Всего откликов: {stats['total']}")
        lines.append(f"• Ожидают ответа: {stats['waiting']}")
        if stats["interview"]:
            lines.append(f"• 🎯 Интервью: {stats['interview']}")
        if stats["offer"]:
            lines.append(f"• 🏆 Оффер: {stats['offer']}")
        lines.append("")
    else:
        lines.append("📋 <b>ОТКЛИКИ:</b> <i>(таблица недоступна)</i>\n")

    if calendar_events:
        lines.append("📅 <b>РАСПИСАНИЕ НА СЕГОДНЯ:</b>")
        for ev in calendar_events:
            lines.append(f"• {ev['time']} — {_esc(ev['summary'])}")
        lines.append("")
    else:
        lines.append("📅 <b>РАСПИСАНИЕ:</b> <i>(событий нет)</i>\n")

    hh_suffix = f" (показано {MAX_PER_SOURCE} из {hh_total})" if hh_total > MAX_PER_SOURCE else ""
    if hh_vacancies:
        lines.append(f"🔍 <b>HH.KZ — новых за {HH_MAX_AGE_H}ч: {hh_total}{hh_suffix}</b>")
        for v in hh_vacancies:
            sal = f" · {_esc(v['salary'])}" if v.get("salary") else ""
            lines.append(f"📌 {_esc(v['title'][:80])}{sal}")
            lines.append(f"🔗 {v['link']}")
        lines.append("")
    else:
        lines.append(f"🔍 <b>HH.KZ:</b> <i>(нет новых за {HH_MAX_AGE_H}ч)</i>\n")

    habr_suffix = f" (показано {MAX_PER_SOURCE} из {habr_total})" if habr_total > MAX_PER_SOURCE else ""
    if habr_vacancies:
        lines.append(f"📰 <b>HABR CAREER — новых за {HABR_MAX_AGE_H}ч: {habr_total}{habr_suffix}</b>")
        for v in habr_vacancies:
            co = f" · {_esc(v['company'])}" if v.get("company") else ""
            lines.append(f"📌 {_esc(v['title'][:80])}{co}")
            lines.append(f"🔗 {v['link']}")
        lines.append("")
    else:
        lines.append(f"📰 <b>HABR CAREER:</b> <i>(нет новых за {HABR_MAX_AGE_H}ч)</i>\n")

    tg_suffix = f" (показано {MAX_TG_POSTS} из {tg_total})" if tg_total > MAX_TG_POSTS else ""
    if tg_vacancies:
        lines.append(f"📢 <b>TELEGRAM — новых за {TG_MAX_AGE_H}ч: {tg_total}{tg_suffix}</b>")
        for v in tg_vacancies:
            preview = v["text"][:120].replace("<", "").replace(">", "").replace("&", "")
            lines.append(f"📌 {_esc(preview)}...")
            lines.append(f"🔗 {v['link']}  (@{v['channel']})")
        lines.append("")
    else:
        lines.append(f"📢 <b>TELEGRAM:</b> <i>(нет новых C++ за {TG_MAX_AGE_H}ч)</i>\n")

    if is_monday:
        if claudedev_posts:
            lines.append("🤖 <b>@CLAUDEDEVOLPER — дайджест недели:</b>")
            for p in claudedev_posts:
                preview = p["text"][:200].replace("<", "").replace(">", "").replace("&", "")
                lines.append(f"• {_esc(preview)}...")
                lines.append(f"  🔗 {p['link']}")
            lines.append("")
        else:
            lines.append("🤖 <b>@CLAUDEDEVOLPER:</b> <i>(ничего полезного за неделю)</i>\n")

    if stats:
        stale_followup = get_stale_followup(stats)
        if stale_followup:
            lines.append("⏰ <b>FOLLOW-UP (раз в 2 нед.):</b>")
            for s in stale_followup:
                lines.append(f"  — {_esc(str(s))}")
            lines.append("")

    lines.append(
        f"<i>Новых: hh={len(hh_vacancies)}/{hh_total}, "
        f"Habr={len(habr_vacancies)}/{habr_total}, TG={len(tg_vacancies)}/{tg_total}</i>"
    )
    lines.append(f"<i>[asyncio v2] {elapsed:.2f} сек · источников: {n_sources}</i>")
    return "\n".join(lines)


# ── Вспомогательные async-заглушки (Python 3.11+ совместимые) ───────────────
async def _empty_dict() -> dict:
    return {}

async def _empty_list() -> list:
    return []


# ── Main ─────────────────────────────────────────────────────────────────────
async def main():
    t0 = time.time()
    now_almaty = datetime.now(ALMATY_TZ)
    date_str   = now_almaty.strftime("%d.%m.%Y")
    time_str   = now_almaty.strftime("%H:%M")
    is_monday  = now_almaty.weekday() == 0

    print(f"[{time_str}] Morning Brief (asyncio v2)...")

    # 1. Google Auth — sync до async loop
    print("  🔐 Токены Google...")
    sheets_token = calendar_token = None
    try:
        sheets_token = get_sheets_token()
    except Exception as e:
        print(f"  ⚠️  Sheets auth: {e}", file=sys.stderr)
    try:
        calendar_token = get_calendar_token()
    except Exception as e:
        print(f"  ⚠️  Calendar auth: {e}", file=sys.stderr)

    n_sources = len(HH_RSS_URLS) + len(HABR_RSS_URLS) + len(TG_CHANNELS) + 3
    print(f"  🚀 {n_sources} источников параллельно...")

    # 2. Все запросы параллельно — TCPConnector ограничивает flood
    # limit=50: при 33+ источниках limit=20 создавал очередь; 50 держит все параллельно
    # limit_per_host=10: hh.kz/habr имеют 8-14 URL каждый
    connector = aiohttp.TCPConnector(limit=50, limit_per_host=10)
    async with aiohttp.ClientSession(connector=connector) as session:

        # return_exceptions=True — один упавший не убивает остальные
        results = await asyncio.gather(
            read_vacancies_async(),
            fetch_calendar_async(session, calendar_token) if calendar_token else _empty_list(),
            fetch_hh_rss_async(session),
            fetch_habr_rss_async(session),
            fetch_tg_vacancies_async(session),
            fetch_claudedev_async(session),
            return_exceptions=True,
        )

        # Безопасно извлекаем каждый результат
        def _safe(val, default):
            return val if not isinstance(val, Exception) else default

        stats           = _safe(results[0], {})
        calendar_events = _safe(results[1], [])
        hh_all          = _safe(results[2], [])
        habr_all        = _safe(results[3], [])
        tg_all          = _safe(results[4], [])
        claudedev_posts = _safe(results[5], [])

        # Логируем ошибки и тихие сбои (пустой ответ там, где ожидаем данные)
        _source_names = ["PG/Stats", "Calendar", "hh.kz", "Habr", "TG", "claudedev"]
        for name, res in zip(_source_names, results):
            if isinstance(res, Exception):
                print(f"  ⚠️  {name} упал: {res}", file=sys.stderr)
            elif name in ("hh.kz", "Habr", "TG") and isinstance(res, list) and len(res) == 0:
                # Пустой список — возможно сайт изменил структуру RSS / заблокировал
                print(f"  ⚠️  {name} вернул 0 результатов — проверь RSS или доступ", file=sys.stderr)

        # Лимит для вывода (все-итого сохраняем для статистики)
        hh_total, habr_total, tg_total = len(hh_all), len(habr_all), len(tg_all)
        hh_vacancies    = hh_all[:MAX_PER_SOURCE]
        habr_vacancies  = habr_all[:MAX_PER_SOURCE]
        tg_vacancies    = tg_all[:MAX_TG_POSTS]

        # ── Сохранение найденных вакансий в PostgreSQL (ON CONFLICT DO NOTHING) ──
        _hh_saved   = _save_vacancies_to_db(hh_all,   "hh.kz")
        _habr_saved = _save_vacancies_to_db(habr_all, "Habr")
        if _hh_saved or _habr_saved:
            print(f"  💾 DB: hh={_hh_saved}, habr={_habr_saved} вакансий сохранено")

        elapsed = time.time() - t0
        print(f"\n  ✅ {elapsed:.2f} сек")
        if stats:
            print(f"     Sheets: {stats['total']} откликов, {stats['waiting']} ожидают, {stats['stale']} зависших")
        print(f"     Календарь: {len(calendar_events)} событий")
        print(f"     hh.kz: {hh_total}, Habr: {habr_total}, TG: {tg_total}")

        # Обновляем telegram_state.json
        _tg_state_file = Path(__file__).parent / "telegram_state.json"
        try:
            _tg_state = json.loads(_tg_state_file.read_text(encoding="utf-8")) \
                if _tg_state_file.exists() else {"seen": {}, "last_run": ""}
            _now_iso = datetime.now(tz=timezone.utc).isoformat()
            for _v in tg_all:
                _tg_state["seen"][_v["post_id"]] = _now_iso
            _tg_state_file.write_text(
                json.dumps(_tg_state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as _e:
            print(f"  [warn] telegram_state.json: {_e}")

        # Формируем сообщение
        message = _build_message(
            date_str, stats, calendar_events, hh_vacancies,
            habr_vacancies, tg_vacancies, claudedev_posts,
            is_monday, elapsed, n_sources,
            hh_total, habr_total, tg_total,
        )

        # Отправляем — с retry при 429
        if len(message) <= MAX_MSG_LEN:
            print(f"\nОтправляю в Telegram ({len(message)} симв.)...")
            await send_telegram_async(session, message)
        else:
            parts, current, current_len = [], [], 0
            for line in message.split("\n"):
                line_len = len(line) + 1
                if current_len + line_len > MAX_MSG_LEN and current:
                    parts.append("\n".join(current))
                    current, current_len = [line], line_len
                else:
                    current.append(line)
 