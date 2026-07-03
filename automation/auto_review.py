#!/usr/bin/env python3
"""
auto_review.py — автоматически проверяет «новые» вакансии из БД
и ставит статус «ignored» на явно нерелевантные по заголовку,
записывая причину в поле notes.

Запуск:  python automation/auto_review.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db.db import Database  # noqa: E402

# ── Наш профиль: что НЕ трогаем ───────────────────────────────────────────────
# Если заголовок содержит хотя бы одно из этих слов — оставляем «новой».

KEEP_PATTERNS: list[re.Pattern[str]] = [p for p in (
    re.compile(r"c\+\+",            re.IGNORECASE),
    re.compile(r"\bqt\b",           re.IGNORECASE),
    re.compile(r"\bembedded\b",     re.IGNORECASE),
    re.compile(r"\bfirmware\b",     re.IGNORECASE),
    re.compile(r"встроенн",         re.IGNORECASE),
    re.compile(r"системный программист", re.IGNORECASE),
    re.compile(r"низкоуровнев",     re.IGNORECASE),
    re.compile(r"\brtos\b",         re.IGNORECASE),
    re.compile(r"mil.std",          re.IGNORECASE),
    re.compile(r"linux.разработчик",re.IGNORECASE),
    re.compile(r"\bfpga\b",         re.IGNORECASE),
    re.compile(r"\bвстраиваем",     re.IGNORECASE),
)]  # type: ignore[list-item]

# ── Правила игнора ─────────────────────────────────────────────────────────────
# Список (паттерн, причина). Первое совпадение — игнор.

def _r(pattern: str, reason: str) -> tuple[re.Pattern[str], str]:
    return re.compile(pattern, re.IGNORECASE), reason


IGNORE_RULES: list[tuple[re.Pattern[str], str]] = [
    # Языки не нашего стека
    _r(r"\bjava\b(?!script)",                           "Java-разработчик (не C++)"),
    _r(r"\b(golang|go\s+developer|go\s+разработчик)\b", "Go/Golang (не C++)"),
    _r(r"\b(ruby|rails)\b",                             "Ruby/Rails (не C++)"),
    _r(r"\bphp\b",                                      "PHP-разработчик (не C++)"),
    _r(r"(\.net|c#|asp\.net|unity3d)",                  ".NET/C# (не C++)"),
    _r(r"\b(react|angular|vue\.?js|node\.?js|typescript|frontend|front.end)\b",
       "Frontend/JS (не C++)"),
    _r(r"\b(kotlin|swift|android\s+developer|ios\s+developer)\b",
       "Mobile (не C++)"),
    _r(r"\b(scala|haskell|erlang|elixir|clojure)\b",   "Функциональный язык (не C++)"),
    _r(r"\b(1[сc]-разработчик|1[сc]\s+разработчик|битрикс)\b",
       "1С/Битрикс (не C++)"),
    _r(r"\b(blockchain|solidity|web3|криптовалют)\b",   "Blockchain/Web3 (не C++)"),

    # Роли без кода
    _r(r"\b(продуктовый аналитик)\b",                    "Аналитик (не разработка)"),
    _r(r"\b(руководитель группы|руководитель отдела)\b",  "Руководитель (не разработка)"),
    _r(r"\b(технический архитектор|ит.архитектор|enterprise архитектор|схемотехник)\b", "Архитектор/Схемотехник (не разработка)"),
    _r(r"\b(администратор проектов)\b",                   "Администратор проектов (не разработка)"),

    # Специализации не в разработке
    _r(r"\b(devops|devsecops|site.reliability|sre)\b",  "DevOps (не разработка)"),
    _r(r"\b(qa\s+engineer|тестировщик|test\s+engineer|quality assurance)\b|функциональн\w+\s+тестирован",
       "QA/Тестирование (не разработка)"),
    _r(r"\b(product manager|product owner|менеджер\s+продукта)\b",
       "Product Manager (не разработка)"),
    _r(r"\bбизнес.аналитик\b",                         "Бизнес-аналитик (не разработка)"),
    _r(r"\bсистемный аналитик\b",                       "Системный аналитик (не разработка)"),
    _r(r"\b(ux|ui\s+designer|дизайнер|graphic\s+designer)\b",
       "Дизайнер (не разработка)"),
    _r(r"\b(маркетолог|seo.специалист|smm|копирайтер)\b",
       "Маркетинг (не разработка)"),
    _r(r"\b(рекрутер|hr\s+manager|talent\s+acquisition)\b|менеджер по подбору",
       "HR/Рекрутинг (не разработка)"),
    _r(r"\b(бухгалтер|финансовый аналитик|экономист)\b",
       "Финансы (не разработка)"),
    _r(r"\b(учитель|преподаватель|педагог|teacher)\b",   "Педагог (не разработка)"),
    _r(r"\b(техническая поддержка|helpdesk|support engineer)\b|тех\.\s*поддержк",
       "Техподдержка (не разработка)"),
    _r(r"\b(сетевой инженер|системный администратор|network engineer|cisco|voip)\b", "Сетевой/Сисадмин (не разработка)"),
    _r(r"\b(data scien|data engineer|аналитик данных|ml engineer|machine learning)\b",
       "Data/ML (не C++)"),

    # Веб-разработка без C++
    _r(r"\bвеб.разработчик\b",                         "Веб-разработчик (не C++)"),
    _r(r"\b(fullstack|full.stack)\b",                   "Full-stack (не C++)"),
    _r(r"\b(wordpress|joomla|1с-битрикс|cms)\b",        "CMS (не C++)"),

    # Совсем другие профессии
    _r(r"\b(продавец|торговый представитель|менеджер по продажам)\b",
       "Продажи (не разработка)"),
    _r(r"\b(геодезист|картограф|кадастровый)\b",        "Геодезия (не разработка)"),
    _r(r"\b(юрист|адвокат|правовед)\b",                 "Юриспруденция (не разработка)"),
]

# ── Логика классификации ────────────────────────────────────────────────────────

def classify(title: str) -> tuple[bool, str]:
    """Возвращает (should_ignore, reason).

    Алгоритм:
    1. Если заголовок содержит наш стек (C++, Qt, embedded…) — НИКОГДА не игнорируем.
    2. Иначе проверяем правила игнора по очереди — первое совпадение = игнор.
    3. Если ни одно не сработало — оставляем новой (требует ручного решения).
    """
    # Наш профиль перекрывает любые правила
    for kp in KEEP_PATTERNS:
        if kp.search(title):
            return False, ""

    for pattern, reason in IGNORE_RULES:
        if pattern.search(title):
            return True, reason

    return False, ""


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Авто-ревью новых вакансий: нерелевантные → игнор"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Показать результат без записи в БД"
    )
    args = parser.parse_args()

    with Database() as db:
        vacancies = db.get_vacancies(status="new", limit=2000)

    total = len(vacancies)
    to_ignore: list[tuple[int, str, str]] = []
    to_keep:   list[str] = []

    for v in vacancies:
        title = v.get("title", "")
        should_ignore, reason = classify(title)
        if should_ignore:
            to_ignore.append((v["id"], title, reason))
        else:
            to_keep.append(title)

    print(f"📋 Всего новых:   {total}")
    print(f"🚫 К игнору:      {len(to_ignore)}")
    print(f"✅ Оставить:      {len(to_keep)}")

    if to_ignore:
        print()
        label = "[DRY-RUN] Были бы проигнорированы" if args.dry_run else "Проигнорированы"
        print(f"──── {label}: ────")
        for vid, title, reason in to_ignore:
            print(f"  [{vid:>5}] {title[:55]:<55} → {reason}")
            if not args.dry_run:
                with Database() as db:
                    db.update_vacancy_status(vid, "ignored", f"Авто-игнор: {reason}")

    if to_keep:
        print()
        print("──── Остались новыми (нужно твоё решение): ────")
        for t in to_keep:
            print(f"  • {t[:80]}")

    if not args.dry_run and to_ignore:
        print(f"\n✅ Обновлено в БД: {len(to_ignore)} вакансий → «игнор»")
    elif args.dry_run:
        print("\nℹ️  Dry-run: БД не изменена")


if __name__ == "__main__":
    main()
