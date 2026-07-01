#!/usr/bin/env python3
"""
check_prompt.py — промт для сессии проверки уведомлений и активности.

Запуск перед сессией проверки:
  python check_prompt.py

Что делает:
  1. Читает PostgreSQL — текущий статус откликов
  2. Формирует промт: что проверить на hh.kz / Habr Career / LinkedIn
  3. Копирует в буфер обмена → вставить в Claude (Ctrl+V)

После сессии запустить:
  python report.py
"""

import subprocess
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from morning_brief import ALMATY_TZ, STALE_DAYS
from db import Database


def read_vacancies_pg() -> dict:
    """Читает статистику вакансий из PostgreSQL."""
    with Database() as db:
        return db.get_vacancy_summary(stale_days=STALE_DAYS)

RESUME_URL = "https://almaty.hh.kz/resume/d2672641ff10710f0e0039ed1f336a336d424b"


def copy_to_clipboard(text: str) -> bool:
    try:
        subprocess.run(["clip"], input=text.encode("utf-16"), check=True, shell=True)
        return True
    except Exception as e:
        print(f"[!] Не удалось скопировать: {e}", file=sys.stderr)
        return False


def build_prompt(stats: dict) -> str:
    now = datetime.now(ALMATY_TZ)
    date_str = now.strftime("%d.%m.%Y %H:%M")
    lines = []

    # ── Контекст ──────────────────────────────────────────────────────────────
    lines.append("Провести сессию проверки уведомлений и активности по поиску работы.")
    lines.append(f"Дата: {date_str}")
    lines.append("")

    # ── Нулевой шаг ───────────────────────────────────────────────────────────
    lines.append("⚡ ПЕРЕД НАЧАЛОМ — запусти run_monitor.bat (мониторинг переговоров hh.kz).")
    lines.append("   Уведомления придут в Telegram автоматически.")
    lines.append("")

    # ── Текущий статус ────────────────────────────────────────────────────────
    lines.append(f"📊 ТЕКУЩИЙ СТАТУС ОТКЛИКОВ:")
    if stats:
        lines.append(f"  • Всего откликов:  {stats['total']}")
        lines.append(f"  • Ожидают ответа:  {stats['waiting']}")
        if stats.get('interview'):
            lines.append(f"  • 🎯 На интервью:  {stats['interview']}")
        if stats.get('offer'):
            lines.append(f"  • 🏆 Оффер:        {stats['offer']}")
        if stats.get('rejected'):
            lines.append(f"  • ❌ Отказов:      {stats['rejected']}")
        if stats.get('stale'):
            lines.append(f"  • ⏰ Зависших (>{STALE_DAYS}д): {stats['stale']}")
    else:
        lines.append("  (PostgreSQL недоступен)")
    lines.append("")

    # ── Зависшие отклики ──────────────────────────────────────────────────────
    if stats.get("stale_list"):
        lines.append(f"⚠️  ЗАВИСШИЕ ОТКЛИКИ (нет ответа {STALE_DAYS}+ дней):")
        for s in stats["stale_list"]:
            lines.append(f"  — {s}")
        lines.append("  → Проверить чат по каждому. Если чат пустой — написать первыми.")
        lines.append("")

    # ── Что проверить ─────────────────────────────────────────────────────────
    lines.append("🔍 ЧТО ПРОВЕРИТЬ (порядок важен):")
    lines.append("")

    lines.append("  1️⃣  hh.kz — Переговоры")
    lines.append("     https://hh.kz/applicant/negotiations")
    lines.append("     ⚡ Читать через get_page_text (не скриншот) — весь список в ~2k токенов")
    lines.append("     • Для каждого отклика: есть ли новое сообщение от работодателя?")
    lines.append("     • Если работодатель задал вопрос → ответить в чате (шаблон A/B/C или своими словами)")
    lines.append("     • Если пригласили на интервью → подтвердить, обновить статус: python add_vacancy.py --url <URL> --status interview")
    lines.append("     • Если отказ → python add_vacancy.py --url <URL> --status rejected")
    lines.append("     • Если зависший чат (нет ответа >7 дней) → написать follow-up:")
    lines.append('       "Добрый день! Хотел уточнить статус по моей кандидатуре. Готов ответить на вопросы."')
    lines.append("")

    lines.append("  2️⃣  Habr Career — Отклики")
    lines.append("     https://career.habr.com/responses")
    lines.append("     • Проверить новые сообщения в каждом отклике")
    lines.append("     • Ответить если что-то спросили")
    lines.append("     • Обновить статусы в БД при изменениях (add_vacancy.py --status)")
    lines.append("")

    lines.append("  3️⃣  LinkedIn — Сообщения и уведомления")
    lines.append("     https://www.linkedin.com/messaging/")
    lines.append("     https://www.linkedin.com/notifications/")
    lines.append("     • Прочитать новые сообщения → ответить на рекрутерские запросы")
    lines.append("     • Проверить принятые connection requests → поблагодарить если уместно")
    lines.append("     • Если рекрутер написал о вакансии → оценить → если релевантна, откликнуться")
    lines.append("")

    lines.append("  4️⃣  Telegram — уведомления n8n-бота")
    lines.append("     • Проверить новые сообщения от бота (вакансии C++ из каналов)")
    lines.append("     • Если есть релевантные → добавить в список для следующей полной сессии")
    lines.append("")

    # ── Обновление БД + зеркало ───────────────────────────────────────────────
    lines.append("📋 ОБНОВЛЕНИЕ ДАННЫХ — по итогу сессии:")
    lines.append("  PostgreSQL (источник правды):")
    lines.append("    python add_vacancy.py --url <URL> --status interview   # интервью")
    lines.append("    python add_vacancy.py --url <URL> --status rejected    # отказ")
    lines.append("    python add_vacancy.py --url <URL> --status offer       # оффер")
    lines.append("  Синхронизация в Google Sheets (зеркало):")
    lines.append("    python sync_to_sheets.py --sheet Вакансии")
    lines.append("  Таблица: https://docs.google.com/spreadsheets/d/1ri78JxboQ477L7nLOmXJupe2ALORwKqbh-jiKuAL8XE/edit")
    lines.append("")

    # ── Финал ─────────────────────────────────────────────────────────────────
    lines.append("✅ В КОНЦЕ СЕССИИ:")
    lines.append("  python report.py")
    lines.append("  → Отправит граффик активности + диаграмму статусов в Telegram")
    lines.append("")

    # ── Технические хинты ─────────────────────────────────────────────────────
    lines.append("⚙️  ТЕХНИЧЕСКИЕ ХИНТЫ:")
    lines.append("  • Одна вкладка — не открывать лишних, переходить через navigate")
    lines.append("  • hh.kz переговоры: navigate → get_page_text (не скриншот!) — ~2k токенов vs ~15k")
    lines.append("  • Если в переговорах есть опрос/тест — пройти его немедленно (get_page_text покажет кнопку «Пройти»)")
    lines.append("  • Не делать скриншот после каждого ответа — достаточно get_page_text")
    lines.append("  • LinkedIn: читать сообщения через get_page_text (быстрее скриншота)")
    lines.append("  • Chrome MCP лимит: ~100-150 вызовов за 5ч — экономить скриншоты")
    lines.append(f"  • Резюме: {RESUME_URL}")

    return "\n".join(lines)


def main():
    print("Собираю данные...\n")

    stats = {}
    try:
        print("  📊 PostgreSQL...", end=" ", flush=True)
        stats = read_vacancies_pg()
        print(f"✓ ({stats['total']} откликов, {stats['waiting']} ожидают, {stats.get('stale', 0)} зависших)")
    except Exception as e:
        print(f"✗ ({e})")

    prompt = build_prompt(stats)

    print()
    print("=" * 60)
    print(prompt)
    print("=" * 60)
    print()

    if copy_to_clipboard(prompt):
        print("✅ Промт скопирован в буфер обмена — вставь в Claude (Ctrl+V)")
    else:
        print("⚠️  Скопируй текст выше вручную")


if __name__ == "__main__":
    main()
