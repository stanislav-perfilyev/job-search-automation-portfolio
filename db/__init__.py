"""
db/ — слой базы данных.
Re-exports для обратной совместимости: from db import Database, JobSearchError
"""
from db.db import Database                             # noqa: F401
from db.exceptions import (                            # noqa: F401
    JobSearchError,
    ConfigError,
    DbConnectionError,
    DbQueryError,
    ApiError,
    HhApiError,
    AnthropicApiError,
    TelegramApiError,
    SheetsError,
    IoError,
)

__all__ = [
    "Database",
    "JobSearchError", "ConfigError",
    "DbConnectionError", "DbQueryError",
    "ApiError", "HhApiError", "AnthropicApiError", "TelegramApiError",
    "SheetsError", "IoError",
]
