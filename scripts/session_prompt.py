#!/usr/bin/env python3
"""
session_prompt.py — генератор динамического промта для сессии поиска работы.

Запуск: python session_prompt.py
Результат: готовый промт копируется в буфер обмена + выводится в консоль.

Использует PostgreSQL (через db.py) для статистики и RSS для новых вакансий.
"""

import sys
import os
import subprocess
from datetime import datetime

# Импортируем из morning_brief.py (лежит рядом)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from morning_brief import (
    fetch_hh_rss,
    fetch_habr_rss,
    ALMATY_TZ,
    HH_MAX_AGE_H,
    HABR_MAX_AGE_H,
    STALE_DAYS,
)
from db import Database


def read_vacancies_pg() -> dict:
    """Читает статистику вакансий из PostgreSQL."""
    with Database() as db:
        return db.get_vacancy_summary(stale_days=STALE_DAYS)

RESUME_URL = "https://almaty.hh.kz/resume/d2672641ff10710f0e0039ed1f336a336d424b"


def copy_to_clipboard(text: str):
    """Копирует текст в буфер обмена Windows."""
    try:
        subprocess.run(
            ["clip"],
            input=text.encode("utf-16"),
            check=True,
            shell=True,
        )
        return True
    except Exception as e:
        print(f"[!] Не удалось скопировать в буфер: {e}", file=sys.stderr)
        return False


def build_prompt(stats: dict, hh: list, habr: list) -> str:
    now = datetime.now(ALMATY_TZ)
    date_str = now.strftime("%d.%m.%Y %H:%M")

    lines = []

    # ── Контекст ──────────────────────────────────────────────────────────────
    lines.append("Веду поиск работы C++ разработчик (удалённо / Алматы).")
    lines.append("Помогай проводить сессию поиска работы по утверждённому воркфлоу v2.")
    lines.append("")

    # ── Нулевой шаг ───────────────────────────────────────────────────────────
    lines.append("⚡ ПЕРЕД НАЧАЛОМ — запусти run_monitor.bat (мониторинг переговоров hh.kz).")
    lines.append("   Уведомления придут в Telegram автоматически.")
    lines.append("")

    # ── События на платформах ─────────────────────────────────────────────────
    lines.append("📬 СОБЫТИЯ НА ПЛАТФОРМАХ — проверить в начале сессии:")
    lines.append("  • hh.kz переговоры:    https://hh.kz/applicant/negotiations")
    lines.append("  • Habr Career отклики: https://career.habr.com/responses")
    lines.append("  • LinkedIn сообщения:  https://www.linkedin.com/messaging/")
    lines.append("  • LinkedIn уведомления: https://www.linkedin.com/notifications/")
    lines.append("")

    # ── Статус таблицы ────────────────────────────────────────────────────────
    lines.append(f"📊 ТЕКУЩИЙ СТАТУС ОТКЛИКОВ (на {date_str}):")
    if stats:
        lines.append(f"  • Всего откликов: {stats['total']}")
        lines.append(f"  • Ожидают ответа: {stats['waiting']}")
        if stats.get("interview"):
            lines.append(f"  • 🎯 На интервью: {stats['interview']}")
        if stats.get("offer"):
            lines.append(f"  • 🏆 Оффер: {stats['offer']}")
        if stats.get("stale"):
            lines.append(f"  • ⏰ Зависших (>{STALE_DAYS} дн.): {stats['stale']}")
            for s in stats.get("stale_list", []):
                lines.append(f"      — {s}")
    else:
        lines.append("  (PostgreSQL недоступен)")
    lines.append("")

    # ── Новые вакансии ────────────────────────────────────────────────────────
    total_new = len(hh) + len(habr)
    lines.append(f"🔍 НОВЫЕ ВАКАНСИИ ЗА ПОСЛЕДНИЕ 24Ч (итого: {total_new}):")

    if hh:
        lines.append(f"  hh.kz — {len(hh)} шт.:")
        for v in hh[:5]:
            sal = f" [{v['salary']}]" if v.get("salary") else ""
            lines.append(f"    • {v['title'][:70]}{sal}")
            lines.append(f"      {v['link']}")
        if len(hh) > 5:
            lines.append(f"    ...ещё {len(hh) - 5}")
    else:
        lines.append(f"  hh.kz — нет новых за {HH_MAX_AGE_H}ч")

    if habr:
        lines.append(f"  Habr Career — {len(habr)} шт.:")
        for v in habr[:5]:
            co = f" · {v['company']}" if v.get("company") else ""
            lines.append(f"    • {v['title'][:70]}{co}")
            lines.append(f"      {v['link']}")
        if len(habr) > 5:
            lines.append(f"    ...ещё {len(habr) - 5}")
    else:
        lines.append(f"  Habr Career — нет новых за {HABR_MAX_AGE_H}ч")
    lines.append("")

    # ── Приоритеты сессии ─────────────────────────────────────────────────────
    lines.append("📋 ПРИОРИТЕТЫ СЕССИИ:")
    if stats and stats.get("stale"):
        lines.append(f"  1. ⚠️  Проверить {stats['stale']} зависших откликов (нет ответа {STALE_DAYS}+ дней)")
    else:
        lines.append("  1. Проверить отклики в статусе «ожидание» — новые чаты от работодателей?")
    if total_new:
        lines.append(f"  2. Откликнуться на {total_new} новых вакансий (приоритет — список выше)")
    lines.append("  3. Записать в PostgreSQL: python batch_add_from_json.py session_vacancies.json")
    lines.append("")

    # ── Инструменты ───────────────────────────────────────────────────────────
    lines.append("🛠 БЫСТРЫЕ ИНСТРУМЕНТЫ:")
    lines.append(f"  • Резюме: {RESUME_URL}")
    lines.append("  • hh.kz вакансии:   https://hh.kz/search/vacancy?text=C%2B%2B&area=40&experience=between1And3")
    lines.append("  • Habr вакансии:    https://career.habr.com/vacancies?q=C%2B%2B&sort=date")
    lines.append("  • GeekJob вакансии: https://geekjob.ru/vacancies/c-plus-plus")
    lines.append("  • LinkedIn поиск C++:  https://www.linkedin.com/jobs/search/?keywords=C%2B%2B%20developer&f_TPR=r86400")
    lines.append("")

    # ── Зарплатные ожидания ───────────────────────────────────────────────────
    lines.append("💰 ЗАРПЛАТНЫЕ ОЖИДАНИЯ:")
    lines.append("  • KZ-работодатель: от 500 000 ₸")
    lines.append("  • RU-работодатель: от 120 000 ₽")
    lines.append("")

    # ── Технические хинты для агента ─────────────────────────────────────────
    lines.append("⚙️  ТЕХНИЧЕСКИЕ ХИНТЫ (для агента):")
    lines.append("")
    lines.append("  СОПРОВОДИТЕЛЬНОЕ ПИСЬМО — ОБЯЗАТЕЛЬНО ДЛЯ КАЖДОГО ОТКЛИКА:")
    lines.append("  • Шаблоны НЕ использовать. Генерировать письмо самостоятельно на основе текста вакансии.")
    lines.append("  • Алгоритм: прочитал вакансию → написал живое персонализированное письмо →")
    lines.append("    вставил через form_input в поле сопроводительного письма.")
    lines.append("  • Стиль: hh.kz / корп. сайты → деловой («Добрый день»), Habr/GeekJob → технический,")
    lines.append("    Upwork → краткий цепляющий (первые 2 строки = суть задачи клиента).")
    lines.append("  • Длина: ~150–200 слов. Без воды и клише («командный игрок», «стрессоустойчив»).")
    lines.append("  • Обязательно упомянуть: конкретный стек из вакансии + релевантный опыт Станислава.")
    lines.append("  • Заканчивать: готовность обсудить детали / открытый вопрос.")
    lines.append("  • Профиль кандидата: C++17/20, Qt, Python, FastAPI, Docker, PostgreSQL,")
    lines.append("    asyncio, Redis, встроенные системы, Telegram-боты. GitHub: https://github.com/stanislav-perfilyev")
    lines.append("")
    lines.append("  ТОП-ВАКАНСИЯ (приоритет A): используй cover_letter.py --top")
    lines.append("  • Признаки: зарплата > KZT 700k / RUB 160k, ИЛИ целевая компания (EPAM,")
    lines.append("    Luxoft, JetBrains, Kaspersky, Тинькофф, Яндекс, МКО Системы, Softeq),")
    lines.append("    ИЛИ идеальный стек (C++/Qt/Embedded + Python + интересная задача).")
    lines.append("  • Флаг --top: Claude Sonnet (~$0.01), длина full (2048 токенов).")
    lines.append("    Упоминает 1-2 GitHub-проекта, цепляется за специфику вакансии,")
    lines.append("    структура: сильный старт → достижения → CTA. Уверенный тон.")
    lines.append("  • Команда: python cover_letter.py --url <URL> --style formal --top")
    lines.append("")
    lines.append("  hh.kz:")
    lines.append("  • ФАЗА 0: переговоры читать через get_page_text на https://hh.kz/applicant/negotiations")
    lines.append("    → НЕ делать скриншот каждой карточки; один get_page_text даёт весь список (~2k токенов)")
    lines.append("    → Если нужна детальная информация по конкретному чату — navigate на его URL")
    lines.append("  • Кликать через `find` по aria-label/ref — надёжнее координат")
    lines.append("  • Обязательное письмо: textarea появляется в диалоге — заполнять через ref")
    lines.append("  • Необязательное письмо: click «Приложить письмо» → textarea → «Отправить»")
    lines.append("  • Проверять состояние через get_page_text, не screenshot (быстрее)")
    lines.append("")
    lines.append("  LinkedIn:")
    lines.append("  • ⚠️  LinkedIn — отдельная мини-сессия, не смешивать с hh.kz (экономия rate limit)")
    lines.append("  • Инвайты — надёжный способ: навигировать на")
    lines.append("      https://www.linkedin.com/preload/search-custom-invite/?vanityName=VANITY")
    lines.append("    Диалог открывается сразу. Vanity name — из href кнопки Connect (JS:)")
    lines.append("      Array.from(document.querySelectorAll('a[aria-label*=\"to connect\"]'))")
    lines.append("        .map(l=>({name:l.getAttribute('aria-label'),href:l.getAttribute('href')}))")
    lines.append("  • Нажимать «Send without a note» координатой [683, 282] или [683, 251]")
    lines.append("")
    lines.append("  Chrome MCP:")
    lines.append("  • При CDP screenshot timeout — сразу get_page_text для проверки состояния")
    lines.append("  • При rate limit 429 (five_hour) — ждать до resetsAt, затем tabs_context_mcp")
    lines.append("  • Лимит Chrome MCP: ~100-150 browser calls за 5ч — экономить скриншоты")
    lines.append("")
    lines.append("  Зеркало Google Sheets:")
    lines.append("  • python sync_to_sheets.py       # обновить все листы из PG")
    lines.append("  • python sync_to_sheets.py --sheet Вакансии   # только вакансии")
    lines.append("  • ТАБЛИЦЫ.bat уже запускает sync автоматически перед открытием Sheets")

    return "\n".join(lines)


def main():
    print("Собираю данные...\n")

    stats = {}
    try:
        print("  📊 PostgreSQL...", end=" ", flush=True)
        stats = read_vacancies_pg()
        print(f"✓ ({stats['total']} откликов)")
    except Exception as e:
        print(f"✗ ({e})")

    hh = []
    try:
        print("  🔍 hh.kz RSS...", end=" ", flush=True)
        hh = fetch_hh_rss()
        print(f"✓ ({len(hh)} новых)")
    except Exception as e:
        print(f"✗ ({e})")

    habr = []
    try:
        print("  📰 Habr Career RSS...", end=" ", flush=True)
        habr = fetch_habr_rss()
        print(f"✓ ({len(habr)} новых)")
    except Exception as e:
        print(f"✗ ({e})")

    print()

    prompt = build_prompt(stats, hh, habr)

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
