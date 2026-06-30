"""
Telegram Channel Monitor — GitHub Actions version
Мониторит Telegram-каналы каждые 4 часа, фильтрует вакансии по keywords,
отправляет уведомление в Telegram-бот.

Улучшения v2:
  - State file (telegram_state.json) — не теряем вакансии при пропуске дней
  - MAX_AGE_HOURS = 72 — окно 3 дня вместо 4.5 часов
  - Фильтр по Google Sheets — пропускаем уже поданные отклики
  - Расширенный поиск: C++, Qt, Embedded + Python, автоматизация, боты, скрапинг
"""

import os
import re
import json
import html
import base64
import tempfile
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Config
TG_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID", "1ri78JxboQ477L7nLOmXJupe2ALORwKqbh-jiKuAL8XE"
)

STATE_FILE = Path(__file__).parent / "telegram_state.json"

CHANNELS = [
    # C++ специализированные
    "cppdevjob", "c_rabota", "forcpp", "runello_rus_c20",
    # IT KZ + широкий охват
    "workitkz", "it_vakansii_jobs", "devs_it", "jc_it",
    # Python / автоматизация (расширение)
    "python_jobs_ru", "pythonist_job", "automation_jobs_ru",
]

KEYWORDS = [
    # ── C++ / Qt / Embedded ──────────────────────────────────────────────────
    "c++", "c/c++", "c++ developer", "c/c++ developer",
    "разработчик c", "developer c", "с++", "с/с++",
    "qt developer", "qt разработчик", "разработчик qt", "pyqt", "qml",
    "embedded", "firmware", "микроконтроллер",
    "stm32", "esp32", "rtos", "freertos",
    "embedded developer", "embedded engineer",
    "системный программист", "low-level", "low level",
    "systems programmer", "kernel developer",
    "driver developer", "разработчик драйверов",
    "c developer", "c/c", "разработчик c/c",
    # ── Python / автоматизация ───────────────────────────────────────────────
    "python developer", "python разработчик", "питон разработчик",
    "python backend", "fastapi developer", "django developer",
    "автоматизация разработчик", "automation engineer", "automation developer",
    "разработчик автоматизации",
    # ── Боты / скрапинг / скрипты ───────────────────────────────────────────
    "telegram bot", "телеграм бот", "бот разработчик", "bot developer",
    "парсинг", "скрапинг", "web scraping", "parsing developer",
    "скрипт разработчик", "script developer",
    # ── DevOps/Linux/Bash (смежные роли) ────────────────────────────────────
    "linux developer", "bash developer", "shell developer",
    "devops python", "python devops",
]

MAX_AGE_HOURS = 72
STATE_PRUNE_DAYS = 30
ALMATY = timezone(timedelta(hours=5))


def load_state():
    if not STATE_FILE.exists():
        return {"seen": {}}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Не удалось загрузить state: {e}")
        return {"seen": {}}


def save_state(state, now):
    cutoff = (now - timedelta(days=STATE_PRUNE_DAYS)).isoformat()
    pruned = {pid: ts for pid, ts in state.get("seen", {}).items() if ts >= cutoff}
    state["seen"] = pruned
    state["last_run"] = now.isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"State сохранён: {len(pruned)} post_id")


def _get_key_file():
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
    local = Path(__file__).parent / "sheets_key.json"
    return local if local.exists() else None


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _get_sheets_token(key_file):
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding as _padding
        USE_CRYPTO = True
    except ImportError:
        USE_CRYPTO = False

    try:
        key_data = json.loads(key_file.read_text())
        sa_email = key_data["client_email"]
        private_key_pem = key_data["private_key"]
        now_ts = int(time.time())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        payload = _b64url(json.dumps({
            "iss": sa_email,
            "scope": "https://www.googleapis.com/auth/spreadsheets.readonly",
            "aud": "https://oauth2.googleapis.com/token",
            "iat": now_ts,
            "exp": now_ts + 3600,
        }).encode())
        signing_input = f"{header}.{payload}".encode()

        if USE_CRYPTO:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            pk = load_pem_private_key(private_key_pem.encode(), password=None)
            signature = pk.sign(signing_input, _padding.PKCS1v15(), hashes.SHA256())
        else:
            return None

        jwt_token = f"{header}.{payload}.{_b64url(signature)}"
        data = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token,
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["access_token"]
    except Exception as e:
        print(f"[Sheets] Ошибка получения токена: {e}")
        return None


def fetch_applied_companies():
    """Читает компании из PostgreSQL для фильтрации дублей в Telegram-мониторе."""
    try:
        from db import Database
        with Database() as db:
            rows = db.get_vacancies(limit=2000)
        companies = set()
        for r in rows:
            company = (r.get("company") or "").strip().lower()
            if len(company) >= 4:
                companies.add(company)
        print(f"[PG] Загружено {len(companies)} компаний для фильтрации")
        return companies
    except Exception as e:
        print(f"[PG] Ошибка загрузки компаний: {e} — фильтрация отключена")
        return set()


def is_already_applied(post_text, applied_companies):
    if not applied_companies:
        return False
    text_lower = post_text.lower()
    for company in applied_companies:
        if len(company) >= 4 and company in text_lower:
            return True
    return False


def fetch_channel(channel):
    url = f"https://t.me/s/{channel}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"[WARN] {channel}: {e}")
        return ""


def strip_tags(text):
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_posts(channel, html_text, now, seen_ids, applied_companies, seen_texts=None):
    """seen_texts — общий set fingerprint'ов для кросс-канальной дедупликации."""
    results = []
    local_seen = set()
    block_re = re.compile(
        r'data-post="([^"]+)"'
        r'[\s\S]*?'
        r'datetime="([^"]+)"'
        r'[\s\S]*?'
        r'class="tgme_widget_message_text[^"]*"[^>]*>'
        r'([\s\S]*?)'
        r'</div>\s*</div>',
        re.MULTILINE,
    )
    for m in block_re.finditer(html_text):
        post_id = m.group(1)
        date_str = m.group(2)
        raw_html = m.group(3)
        if post_id in local_seen:
            continue
        local_seen.add(post_id)
        if post_id in seen_ids:
            continue
        try:
            post_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        age_hours = (now - post_time).total_seconds() / 3600
        if age_hours > MAX_AGE_HOURS or age_hours < 0:
            continue
        text = strip_tags(raw_html)
        text_lower = text.lower()
        seen_ids.add(post_id)
        if not any(kw in text_lower for kw in KEYWORDS):
            continue
        if is_already_applied(text, applied_companies):
            print(f"  [Sheets filter] Пропуск: {post_id}")
            continue
        # Кросс-канальный дубль
        if seen_texts is not None:
            fp = text[:80].strip()
            if fp in seen_texts:
                continue
            seen_texts.add(fp)
        results.append({
            "channel": channel,
            "post_id": post_id,
            "text": text,
            "link": f"https://t.me/{post_id}",
            "date": date_str,
        })
    return results


def send_telegram(message):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[ERROR] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы")
        return False
    payload = json.dumps({
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[ERROR] Telegram: {e}")
        return False


def main():
    now = datetime.now(tz=timezone.utc)
    now_almaty = now.astimezone(ALMATY).strftime("%d.%m.%Y %H:%M")
    print(f"=== Telegram Monitor v2 [{now_almaty} Алматы] ===")
    print(f"Каналов: {len(CHANNELS)}, окно: {MAX_AGE_HOURS} ч\n")

    state = load_state()
    seen_ids = set(state.get("seen", {}).keys())
    print(f"State: {len(seen_ids)} уже виденных постов")

    applied_companies = fetch_applied_companies()
    vacancies = []

    seen_texts = set()   # кросс-канальная дедупликация
    for channel in CHANNELS:
        print(f"  Проверяю @{channel}...", end=" ")
        page = fetch_channel(channel)
        if not page:
            print("пропущен")
            continue
        count_before = len(seen_ids)
        posts = parse_posts(channel, page, now, seen_ids, applied_companies, seen_texts)
        print(f"{len(posts)} новых вак. ({len(seen_ids) - count_before} проверено)")
        vacancies.extend(posts)

    state["seen"] = {pid: now.isoformat() for pid in seen_ids}
    save_state(state, now)

    print(f"\nИтого: {len(vacancies)} новых вакансий")
    if not vacancies:
        print("Нечего отправлять.")
        return

    MAX_LEN = 4000

    def make_block(v):
        preview = (v["text"][:200]
                   .replace("*", "").replace("_", "").replace("`", "")
                   .replace("[", "").replace("]", ""))
        return f"*{v['channel']}*\n{preview}\n{v['link']}\n"

    header = f"*Новые вакансии C++/Qt/Embedded: {len(vacancies)} шт.*\n_{now_almaty} (Алматы)_\n\n"
    blocks = [make_block(v) for v in vacancies]
    full = header + "\n".join(blocks)

    if len(full) <= MAX_LEN:
        ok = send_telegram(full)
        print("Telegram: OK" if ok else "Telegram: ошибка")
    else:
        send_telegram(header.strip())
        for v in vacancies:
            send_telegram(make_block(v).strip())
        print(f"Telegram: отправлено {len(vacancies)+1} сообщений")


if __name__ == "__main__":
    main()
