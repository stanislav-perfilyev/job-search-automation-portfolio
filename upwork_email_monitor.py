#!/usr/bin/env python3
"""
upwork_email_monitor.py — мониторинг писем Upwork через Gmail IMAP.

Запускается из GitHub Actions каждые 30 минут.
Ищет письма от Upwork за последние 35 минут.
Отправляет уведомления в Telegram при важных событиях.

Переменные окружения:
  GMAIL_ADDRESS       — stasperfiliyev@gmail.com
  GMAIL_APP_PASSWORD  — App Password из Google Account (не обычный пароль)
  TELEGRAM_BOT_TOKEN  — токен бота
  TELEGRAM_CHAT_ID    — ID чата

Установка:
  pip install requests
"""

import imaplib
import socket
import email
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from email.utils import parsedate_to_datetime

import requests

# ── Конфигурация ──────────────────────────────────────────────────────────────
GMAIL_ADDRESS      = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
BOT_TOKEN          = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID            = os.environ.get("TELEGRAM_CHAT_ID", "")

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Смотрим письма за последние N минут (с запасом над кроном 30 мин)
LOOKBACK_MINUTES = 35

# Отправители Upwork
UPWORK_SENDERS = (
    "upwork.com",
    "noreply@upwork.com",
    "notifications@upwork.com",
    "do-not-reply@upwork.com",
    "support@upwork.com",
)

# ── Карта событий: (ключевые слова в теме) → (эмодзи, описание, приоритет) ──
# Приоритет: 1=критично (контракт), 2=важно (сообщение), 3=инфо (просмотр)
EVENTS = [
    # Контракт / найм
    (["contract has started", "hired you", "you've been hired", "congratulations"],
     "🎉🎉🎉 КОНТРАКТ НАЧАТ", 1),
    # Оффер
    (["offer has been extended", "sent you an offer", "new offer"],
     "📋 ОФФЕР ПОЛУЧЕН", 1),
    # Приглашение на интервью
    (["invited you to interview", "invitation to interview", "you've been invited"],
     "🎯 Приглашение на интервью", 1),
    # Новое сообщение от клиента
    (["new message", "sent you a message", "has replied", "messaged you"],
     "💬 Новое сообщение от клиента", 2),
    # Отклик просмотрен
    (["viewed your proposal", "proposal was viewed", "looked at your proposal"],
     "👀 Отклик просмотрен", 3),
    # Shortlist
    (["shortlisted", "shortlist"],
     "⭐ Добавлен в шортлист", 2),
    # Интервью
    (["interview", "want to connect"],
     "🔔 Запрос на интервью", 1),
]

# Минимальный приоритет для отправки (1=только критичное, 3=всё)
MIN_PRIORITY = 3


# ── Утилиты ───────────────────────────────────────────────────────────────────

def decode_str(s: str) -> str:
    """Декодирует encoded-word строку из заголовка письма."""
    parts = decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def classify_event(subject: str) -> tuple[str, int] | None:
    """Возвращает (описание, приоритет) или None если неинтересное письмо."""
    subj_lower = subject.lower()
    for keywords, label, priority in EVENTS:
        if any(kw in subj_lower for kw in keywords):
            return label, priority
    return None


def is_upwork_sender(from_header: str) -> bool:
    """Проверяет что письмо от Upwork."""
    from_lower = from_header.lower()
    return any(s in from_lower for s in UPWORK_SENDERS)


def send_telegram(text: str) -> bool:
    """Отправляет сообщение в Telegram."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  ❌ Telegram error: {e}")
        return False


def parse_email_date(msg) -> datetime | None:
    """Парсит дату письма в aware datetime (UTC)."""
    date_str = msg.get("Date", "")
    if not date_str:
        return None
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


# ── Основная логика ────────────────────────────────────────────────────────────

def check_emails() -> list[dict]:
    """Подключается к Gmail, возвращает список событий за LOOKBACK_MINUTES."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)

    # Формат даты для IMAP SINCE (без времени, день включительно)
    since_str = cutoff.strftime("%d-%b-%Y")

    print(f"🔍 Подключаюсь к Gmail IMAP...")
    socket.setdefaulttimeout(30)
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    mail.select("INBOX")

    # Ищем письма от Upwork за сегодня/вчера
    _, data = mail.search(None, f'(FROM "upwork.com" SINCE "{since_str}")')
    ids = data[0].split() if data[0] else []
    print(f"   Найдено писем от Upwork за {since_str}: {len(ids)}")

    events = []
    for uid in ids:
        _, msg_data = mail.fetch(uid, "(RFC822)")
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        # Дата письма
        dt = parse_email_date(msg)
        if dt and dt < cutoff:
            continue  # старее нашего окна

        subject = decode_str(msg.get("Subject", ""))
        from_h  = decode_str(msg.get("From", ""))

        print(f"   📧 [{dt.strftime('%H:%M') if dt else '??:??'}] {subject[:70]}")

        if not is_upwork_sender(from_h):
            continue

        classified = classify_event(subject)
        if classified is None:
            print(f"      → пропускаем (не в карте событий)")
            continue

        label, priority = classified
        if priority > MIN_PRIORITY:
            print(f"      → низкий приоритет ({priority}), пропускаем")
            continue

        events.append({
            "subject": subject,
            "from": from_h,
            "date": dt,
            "label": label,
            "priority": priority,
        })
        print(f"      ✅ событие: {label}")

    mail.logout()
    return events


def format_message(event: dict) -> str:
    """Форматирует Telegram-сообщение для события."""
    dt_str = ""
    if event["date"]:
        # UTC+5 (Алматы)
        local_dt = event["date"] + timedelta(hours=5)
        dt_str = local_dt.strftime("%d.%m %H:%M")

    lines = [
        "📨 <b>Upwork Monitor</b> · <code>upwork_email_monitor.py</code>",
        "",
        f"<b>UPWORK</b> {event['label']}",
        "",
        f"📌 <b>Тема:</b> {event['subject']}",
        f"🕐 <b>Время:</b> {dt_str} (АЛМ)",
        "",
        "👉 <a href=\"https://www.upwork.com/ab/proposals/\">Открыть предложения</a>",
        "👉 <a href=\"https://www.upwork.com/ab/messages/\">Открыть сообщения</a>",
    ]
    return "\n".join(lines)


def main():
    # Проверяем конфигурацию
    missing = []
    if not GMAIL_ADDRESS:      missing.append("GMAIL_ADDRESS")
    if not GMAIL_APP_PASSWORD: missing.append("GMAIL_APP_PASSWORD")
    if not BOT_TOKEN:          missing.append("TELEGRAM_BOT_TOKEN")
    if not CHAT_ID:            missing.append("TELEGRAM_CHAT_ID")
    if missing:
        print(f"❌ Не заданы переменные: {', '.join(missing)}")
        sys.exit(1)

    print(f"⏰ Мониторинг Upwork emails | окно: последние {LOOKBACK_MINUTES} мин")
    print(f"📧 Gmail: {GMAIL_ADDRESS}")

    try:
        events = check_emails()
    except Exception as e:
        print(f"❌ Ошибка IMAP: {e}")
        # Шлём алерт об ошибке мониторинга
        send_telegram(f"⚠️ <b>Upwork Monitor — ошибка</b>\n\n<code>{e}</code>")
        sys.exit(1)

    if not events:
        print(f"\n✅ Новых событий Upwork нет.")
        sys.exit(0)

    # Сортируем по приоритету, затем по времени
    events.sort(key=lambda e: (e["priority"], e["date"] or datetime.min.replace(tzinfo=timezone.utc)))

    print(f"\n📨 Отправляю {len(events)} уведомлений в Telegram...")
    sent = 0
    for ev in events:
        msg = format_message(ev)
        if send_telegram(msg):
            sent += 1
            print(f"  ✅ {ev['label']}")
        else:
            print(f"  ❌ Не отправлено: {ev['label']}")

    print(f"\n{'─'*40}")
    print(f"Отправлено: {sent}/{len(events)}")


if __name__ == "__main__":
    main()
