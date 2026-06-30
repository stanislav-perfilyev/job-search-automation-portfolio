#!/usr/bin/env python3
"""
exceptions.py — иерархия кастомных исключений job-search проекта.

Структура:
    JobSearchError          # базовый класс (все ловим его в main)
    ├── ConfigError         # неверная конфигурация / отсутствует env var
    ├── DbConnectionError   # не удалось подключиться к PostgreSQL
    ├── DbQueryError        # ошибка SQL-запроса
    ├── ApiError            # внешний API вернул ошибку (HH, Anthropic, Telegram)
    │   ├── HhApiError
    │   ├── AnthropicApiError
    │   └── TelegramApiError
    ├── SheetsError         # Google Sheets API
    └── IoError             # файловые операции

Использование::

    from exceptions import DbConnectionError, ApiError

    try:
        db.connect()
    except DbConnectionError as exc:
        logger.critical("DB unavailable: %s", exc)
        sys.exit(1)
"""

from __future__ import annotations


class JobSearchError(Exception):
    """Базовый класс для всех исключений проекта."""


# ── Конфигурация ─────────────────────────────────────────────────────────────


class ConfigError(JobSearchError):
    """Отсутствует или некорректна переменная окружения / конфигурационный файл."""


# ── База данных ───────────────────────────────────────────────────────────────


class DbConnectionError(JobSearchError):
    """Не удалось установить соединение с PostgreSQL."""


class DbQueryError(JobSearchError):
    """Ошибка выполнения SQL-запроса (конкретный текст в .args[0])."""


# ── Внешние API ───────────────────────────────────────────────────────────────


class ApiError(JobSearchError):
    """Внешний API вернул ошибку или недоступен."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    def __str__(self) -> str:
        if self.status_code is not None:
            return f"[HTTP {self.status_code}] {super().__str__()}"
        return super().__str__()


class HhApiError(ApiError):
    """Ошибка API HeadHunter (hh.kz / hh.ru)."""


class AnthropicApiError(ApiError):
    """Ошибка API Anthropic Claude."""


class TelegramApiError(ApiError):
    """Ошибка Telegram Bot API."""


# ── Google Sheets ─────────────────────────────────────────────────────────────


class SheetsError(JobSearchError):
    """Ошибка работы с Google Sheets API."""


# ── Файловые операции ─────────────────────────────────────────────────────────


class IoError(JobSearchError):
    """Ошибка чтения / записи файла."""
