"""
Telegram Channel Monitor — GitHub Actions version
Порт n8n workflow: мониторит 8 Telegram-каналов каждые 4 часа,
фильтрует C++ вакансии, отправляет уведомление в Telegram-бот.
"""

import os
import re
import html
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ── Конфиг ──────────────────────────────────────────────────────────────────
TG_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

CHANNELS = [
    # Tier 1 — C++ специализированные
    "cppdevjob",
    "c_rabota",
    "forcpp",
    "runello_rus_c20",
    # Tier 2 — IT KZ + широкий
    "workitkz",
    "it_vakansii_jobs",
    "devs_it",
    "jc_it",
]

KEYWORDS = [
    "c++", "c/c++", "qt", "embedded", "firmware",
    "микроконтроллер", "stm32", "esp32", "rtos",
    "разработчик c", "developer c", "c developer",
    "c++ developer", "c/c++ developer",
]

# Смотрим посты не старше MAX_AGE_HOURS + буфер на задержки CI
MAX_AGE_HOURS = 4.5

ALMATY = timezone(timedelta(hours=5))


# ── Утилиты ──────────────────────────────────────────────────────────────────

def fetch_channel(channel: str) -> str:
    url = f"https://t.me/s/{channel}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"[WARN] {channel}: {e}")
        return ""


def strip_tags(text: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_posts(channel: str, html_text: str, now: datetime) -> list[dict]:
    """Извлекает посты из HTML страницы t.me/s/{channel}."""
    results = []
    seen = set()

    # Блок поста: data-post="channel/id" ... datetime="..." ... tgme_widget_message_text
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
        post_id = m.group(1)   # e.g. "cppdevjob/2443"
        date_str = m.group(2)  # ISO 8601
        raw_html = m.group(3)

        if post_id in seen:
            continue
        seen.add(post_id)

        # Возраст поста
        try:
            post_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            continue
        age_hours = (now - post_time).total_seconds() / 3600
        if age_hours > MAX_AGE_HOURS or age_hours < 0:
            continue

        text = strip_tags(raw_html)
        text_lower = text.lower()

        if not any(kw in text_lower for kw in KEYWORDS):
            continue

        results.append({
            "channel": channel,
            "post_id": post_id,
            "text": text,
            "link": f"https://t.me/{post_id}",
            "date": date_str,
        })

    return results


def send_telegram(message: str) -> bool:
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[ERROR] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы")
        return False

    import json
    payload = json.dumps({
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[ERROR] Telegram sendMessage: {e}")
        return False


# ── Основная логика ───────────────────────────────────────────────────────────

def main():
    now = datetime.now(tz=timezone.utc)
    now_almaty = now.astimezone(ALMATY).strftime("%d.%m.%Y %H:%M")

    print(f"=== Telegram Monitor [{now_almaty} Алматы] ===")
    print(f"Каналов: {len(CHANNELS)}, окно: {MAX_AGE_HOURS} ч\n")

    vacancies = []
    for channel in CHANNELS:
        print(f"  Проверяю @{channel}...", end=" ")
        page = fetch_channel(channel)
        if not page:
            print("пропущен")
            continue
        posts = parse_posts(channel, page, now)
        print(f"{len(posts)} вак.")
        vacancies.extend(posts)

    print(f"\nИтого: {len(vacancies)} новых вакансий C++")

    if not vacancies:
        print("Нечего отправлять.")
        return

    # Форматируем сообщение (Telegram limit ~4096 chars)
    lines = [f"🔔 *Новые вакансии C++: {len(vacancies)} шт.*", f"_{now_almaty} (Алматы)_", ""]
    for v in vacancies[:8]:
        preview = v["text"][:150].replace("*", "").replace("_", "").replace("`", "")
        lines.append(f"📌 {preview}")
        lines.append(f"🔗 {v['link']}")
        lines.append(f"📢 @{v['channel']}")
        lines.append("")
    if len(vacancies) > 8:
        lines.append(f"_...и ещё {len(vacancies) - 8} вакансий_")

    message = "\n".join(lines)

    ok = send_telegram(message)
    print("Telegram: ✅ отправлено" if ok else "Telegram: ❌ ошибка")


if __name__ == "__main__":
    main()
