#!/usr/bin/env python3
"""
cover_letter.py — генератор сопроводительных писем через Claude API.

Зависимости:
  pip install anthropic httpx

Использование:
  python cover_letter.py --text "описание вакансии" --style upwork --length short
  python cover_letter.py --url "https://hh.kz/vacancy/..." --style formal --length standard
  python cover_letter.py --url "..." --top           # ТОП-вакансия: sonnet + full + портфолио
  python cover_letter.py --text "..." --style technical --length full --lang en
  python cover_letter.py --history
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import httpx

try:
    import anthropic
    # issubclass проверяет, что это настоящие классы исключений, а не Mock-объекты
    _AnthropicAuthError    = anthropic.AuthenticationError
    _AnthropicRateLimitErr = anthropic.RateLimitError
    _AnthropicAPIError     = anthropic.APIStatusError
    assert issubclass(_AnthropicAuthError,    BaseException)
    assert issubclass(_AnthropicRateLimitErr, BaseException)
    assert issubclass(_AnthropicAPIError,     BaseException)
except ImportError:
    print("Установите пакет: pip install anthropic")
    sys.exit(1)
except (AssertionError, TypeError, AttributeError):
    # Запасные классы на случай старой версии пакета или mock-окружения тестов
    class _AnthropicAuthError(Exception): pass      # type: ignore
    class _AnthropicRateLimitErr(Exception): pass   # type: ignore
    class _AnthropicAPIError(Exception): pass       # type: ignore


def _load_dotenv() -> None:
    """Загружает переменные из .env (только те, которых ещё нет в окружении)."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

# ── Константы ──────────────────────────────────────────────────────────────

HISTORY_FILE = Path(__file__).parent / "cover_letters.json"
MODEL        = "claude-haiku-4-5-20251001"   # стандартный (быстро, дёшево)
MODEL_TOP    = "claude-sonnet-4-6"            # топ-вакансии (~$0.01/письмо, умнее)

LENGTH_WORDS: dict[str, int] = {
    "short":    150,
    "standard": 250,
    "full":     400,
}

STYLE_DESCRIPTIONS: dict[str, str] = {
    "formal": (
        "формальный корпоративный тон, официальное обращение «Добрый день» / «Dear Hiring Team», "
        "структура: приветствие → релевантный опыт → мотивация работать именно здесь → призыв к действию"
    ),
    "technical": (
        "технический тон стартапа, меньше формальностей, акцент на конкретном стеке и решённых задачах, "
        "показывай мышление инженера, а не менеджера"
    ),
    "upwork": (
        "краткий Upwork-стиль: первые 1-2 строки сразу цепляют (покажи что понял задачу клиента), "
        "далее — конкретные результаты без воды, завершай открытым вопросом или предложением обсудить"
    ),
}

CANDIDATE_PROFILE = """
Имя: Станислав (Stanislav)
Специализация: C++17/20, Python 3, Qt, встроенные системы
Коммерческий опыт: разработка ПО, автоматизация процессов, Telegram-боты, бэкенд на FastAPI
Стек: C++, Python, Qt, Docker, PostgreSQL, FastAPI, asyncio, Redis, SQLAlchemy
Языки: Русский — родной, English — B2 (документация, код, созвоны)
GitHub: https://github.com/stanislav-perfilyev
Целевые рынки: Россия (от 120 000 руб/мес), Казахстан (от 500 000 тенге/мес)
""".strip()

# Портфолио-проекты — используются в режиме --top
PORTFOLIO_PROJECTS = """
Проекты на GitHub (github.com/stanislav-perfilyev):
1. job-search-automation — Python/FastAPI: система автоматизации поиска работы с PostgreSQL,
   Redis, Telegram-ботом, Google Sheets API, Docker. Production на Railway.
2. mil1553_analyzer — Delphi/Object Pascal: анализатор протокола MIL-STD-1553B (МКО).
   State machine декодер, симулятор трафика, DUnit тесты.
3. C++ Embedded: разработка многопоточного планировщика на C++17 с Qt-интерфейсом,
   исправление race condition в файловых потоках (HFileThreads.cpp).
""".strip()


# ── Утилиты ────────────────────────────────────────────────────────────────

def detect_language(text: str) -> str:
    """Определяет язык вакансии по доле кириллицы."""
    if not text:
        return "en"
    cyrillic = sum(1 for c in text if "\u0400" <= c <= "\u04ff")
    ratio = cyrillic / len(text)
    return "ru" if ratio > 0.05 else "en"


def fetch_url(url: str) -> str:
    """Загружает страницу вакансии и возвращает очищенный текст."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        print(f"HTTP {exc.response.status_code} при загрузке {url}")
        sys.exit(1)
    except httpx.HTTPError as exc:
        print(f"Ошибка загрузки URL: {exc}")
        sys.exit(1)

    text = re.sub(r"<[^>]+>", " ", resp.text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:8000]


def extract_title(vacancy_text: str) -> str:
    """Извлекает заголовок из первой строки текста вакансии."""
    first = vacancy_text.strip().splitlines()[0] if vacancy_text.strip() else ""
    return first[:80].strip() or "Без названия"


def load_history() -> list[dict]:
    """Загружает историю писем из JSON-файла."""
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_history(history: list[dict]) -> None:
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_to_history(record: dict) -> None:
    history = load_history()
    history.append(record)
    save_history(history)
    print(f"Сохранено в {HISTORY_FILE.name} (всего записей: {len(history)})")


# ── Генерация ──────────────────────────────────────────────────────────────

def build_prompt(
    vacancy_text: str,
    style: str,
    length: str,
    lang: str,
    top_vacancy: bool = False,
) -> tuple[str, str]:
    """
    Возвращает (system_prompt, user_prompt).

    top_vacancy=True — режим «топ-вакансия»: расширенный промпт с упоминанием
    конкретных GitHub-проектов, более творческий и индивидуальный тон.
    """
    words = LENGTH_WORDS[length]
    style_desc = STYLE_DESCRIPTIONS[style]

    lang_instruction = (
        "Пиши письмо на РУССКОМ языке."
        if lang == "ru"
        else "Write the letter in ENGLISH."
    )

    base_rules = (
        f"- {lang_instruction}\n"
        f"- Стиль: {style_desc}\n"
        f"- Длина: ровно ~{words} слов (+-15%). Следи за объёмом.\n"
        f"- Персонализируй под конкретную вакансию: упомяни технологии и задачи из описания.\n"
        f"- Используй только реальный опыт из профиля — не придумывай несуществующий.\n"
        f"- Не упоминай зарплатные ожидания.\n"
        f"- Не используй избитые фразы: «командный игрок», «стрессоустойчивый», «быстро обучаюсь».\n"
        f"- ЗАПРЕЩЕНО начинать с «Привет» или любого другого фамильярного обращения. "
        f"Начинай с «Добрый день» / «Здравствуйте» (RU) или «Dear Hiring Team» / «Hello» (EN).\n"
        f"- Верни ТОЛЬКО текст письма — без заголовков, объяснений и метакомментариев."
    )

    if top_vacancy:
        top_rules = (
            f"\n\n--- РЕЖИМ ТОП-ВАКАНСИИ — максимальное качество ---\n"
            f"- Это письмо для очень интересной вакансии — вложи максимум творчества.\n"
            f"- Упомяни 1-2 конкретных проекта из портфолио, наиболее релевантных данной вакансии.\n"
            f"- Покажи, что кандидат изучил компанию: найди в тексте вакансии что-то специфичное "
            f"(технология, продукт, задача) и упомяни это конкретно — без общих слов.\n"
            f"- Структура: мощный зацепляющий открывающий абзац (НЕ «Добрый день, меня зовут...») → "
            f"2-3 абзаца с конкретными достижениями и стеком → финал с призывом к действию.\n"
            f"- Финал: не «жду ответа», а конкретный открытый вопрос или предложение созвона.\n"
            f"- Тон: уверенный, не заискивающий — кандидат сильный, а не проситель.\n"
        )
        profile_section = (
            f"Профиль кандидата:\n{CANDIDATE_PROFILE}\n\n"
            f"Портфолио:\n{PORTFOLIO_PROJECTS}"
        )
    else:
        top_rules = ""
        profile_section = f"Профиль кандидата:\n{CANDIDATE_PROFILE}"

    system = (
        f"Ты помогаешь составлять сопроводительные письма для IT-разработчика.\n\n"
        f"{profile_section}\n\n"
        f"Правила написания:\n"
        f"{base_rules}"
        f"{top_rules}"
    )

    user = f"Описание вакансии:\n\n{vacancy_text}\n\nНапиши сопроводительное письмо."

    return system, user


def generate(
    vacancy_text: str,
    style: str,
    length: str,
    lang: str,
    top_vacancy: bool = False,
) -> str:
    """
    Генерирует письмо через Claude API.

    top_vacancy=True:
      - claude-sonnet-4-6 вместо haiku (~$0.01 за письмо, умнее)
      - расширенный промпт: упоминание портфолио, более творческий тон
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Не задана переменная ANTHROPIC_API_KEY.")
        print("   Добавь в .env: ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    model = MODEL_TOP if top_vacancy else MODEL
    client = anthropic.Anthropic(api_key=api_key)
    system_prompt, user_prompt = build_prompt(vacancy_text, style, length, lang, top_vacancy)

    mode_label = "ТОП-ВАКАНСИЯ" if top_vacancy else "стандарт"
    print(f"Генерирую письмо ({style}, {length}, {lang.upper()}, {mode_label})...")
    if top_vacancy:
        print(f"   Модель: {model} (sonnet — выше качество)")

    try:
        message = client.messages.create(
            model=model,
            max_tokens=2048 if top_vacancy else 1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except _AnthropicAuthError:
        print("Неверный ANTHROPIC_API_KEY — проверь .env файл")
        sys.exit(1)
    except _AnthropicRateLimitErr:
        print("Rate limit API — подожди минуту и повтори")
        sys.exit(1)
    except _AnthropicAPIError as exc:
        detail = getattr(exc, "status_code", "?")
        msg    = getattr(exc, "message", str(exc))
        print(f"Claude API статус {detail}: {msg}")
        sys.exit(1)
    except Exception as exc:
        print(f"Непредвиденная ошибка Claude API: {type(exc).__name__}: {exc}")
        sys.exit(1)

    return message.content[0].text.strip()


# ── CLI ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Генератор сопроводительных писем через Claude API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "примеры:\n"
            "  python cover_letter.py --text \"Ищем C++ разработчика...\" --style formal --length standard\n"
            "  python cover_letter.py --url \"https://hh.kz/vacancy/123\" --style upwork --length short\n"
            "  python cover_letter.py --url \"...\" --top          # ТОП: sonnet + full + портфолио\n"
            "  python cover_letter.py --text \"...\" --style technical --length full --lang en\n"
            "  python cover_letter.py --history"
        ),
    )

    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--text", "-t", metavar="TEXT", help="Текст описания вакансии")
    source.add_argument("--url",  "-u", metavar="URL",  help="URL страницы вакансии")

    parser.add_argument(
        "--style", "-s",
        choices=["formal", "technical", "upwork"],
        default="formal",
        help="Тон: formal (корпоратив), technical (стартап), upwork (краткий). По умолч.: formal",
    )
    parser.add_argument(
        "--length", "-l",
        choices=["short", "standard", "full"],
        default="standard",
        help="Длина: short (~150 слов), standard (~250), full (~400). По умолч.: standard",
    )
    parser.add_argument(
        "--lang",
        choices=["ru", "en", "auto"],
        default="auto",
        help="Язык письма (auto = автодетект по тексту вакансии). По умолч.: auto",
    )
    parser.add_argument(
        "--top",
        action="store_true",
        help=(
            "Режим ТОП-вакансии: claude-sonnet (умнее), длина=full, "
            "упоминает GitHub-проекты, максимально персонализированный тон. "
            "Переопределяет --length в full."
        ),
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Не сохранять результат в cover_letters.json",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Показать последние 5 записей истории и выйти",
    )
    return parser.parse_args()


def show_history() -> None:
    history = load_history()
    if not history:
        print("История пуста.")
        return
    last = history[-5:][::-1]
    print(f"\nПоследние {len(last)} из {len(history)} записей:\n")
    for rec in last:
        lang_flag = "RU" if rec.get("lang") == "ru" else "EN"
        top_mark = " [TOP]" if rec.get("top_vacancy") else ""
        print(
            f"  {lang_flag}{top_mark} [{rec.get('date', '?')}] {rec.get('vacancy_title', '?')}\n"
            f"     style={rec.get('style')}  length={rec.get('length')}"
        )
        if rec.get("source_url"):
            print(f"     url={rec['source_url']}")
        print()


def main() -> None:
    args = parse_args()

    if args.history:
        show_history()
        return

    if not args.text and not args.url:
        print("Укажи --text или --url (либо --history для просмотра истории).")
        sys.exit(1)

    # Загружаем текст вакансии
    if args.url:
        print(f"Загружаю {args.url}...")
        vacancy_text = fetch_url(args.url)
    else:
        vacancy_text = args.text

    if not vacancy_text.strip():
        print("Текст вакансии пустой.")
        sys.exit(1)

    # --top переопределяет length в full
    if args.top and args.length != "full":
        print(f"--top: переопределяю длину {args.length} -> full")
        args.length = "full"

    # Определяем язык
    lang = args.lang if args.lang != "auto" else detect_language(vacancy_text)
    lang_label = "Русский" if lang == "ru" else "English"
    auto_label  = " (автодетект)" if args.lang == "auto" else ""
    print(f"Язык: {lang_label}{auto_label}")

    # Генерируем
    letter = generate(vacancy_text, args.style, args.length, lang, top_vacancy=args.top)

    # Выводим
    separator = "-" * 60
    print(f"\n{separator}")
    print(letter)
    print(f"{separator}\n")

    words = len(letter.split())
    target = LENGTH_WORDS[args.length]
    diff = words - target
    sign = "+" if diff > 0 else ""
    print(f"Слов: {words} (цель {target}, отклонение {sign}{diff})")

    # Сохраняем историю
    if not args.no_save:
        title = extract_title(vacancy_text)
        record = {
            "date":          datetime.now().strftime("%Y-%m-%d %H:%M"),
            "vacancy_title": title,
            "source_url":    args.url or "",
            "style":         args.style,
            "length":        args.length,
            "lang":          lang,
            "top_vacancy":   args.top,
            "letter":        letter,
        }
        append_to_history(record)


if __name__ == "__main__":
    main()
