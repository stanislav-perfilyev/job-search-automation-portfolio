#!/usr/bin/env python3
"""
sync_to_sheets.py — зеркалирование PostgreSQL → Google Sheets.

Читает все данные из PG, перезаписывает листы Sheets с красивым
форматированием и добавляет графики эффективности.

Листы:
  Вакансии  — вакансии по статусу + pie-chart статусов + bar-chart источников
  Фриланс   — проекты + bar-chart по платформам
  Статистика — daily_stats + line-chart активности
  Skill Gap  — топ пробелов скиллов
  Dashboard  — сводные KPI

Запуск:
  python sync_to_sheets.py
  python sync_to_sheets.py --sheet Вакансии   # только один лист
  python sync_to_sheets.py --no-charts        # без графиков (быстрее)
"""

import argparse
import base64
import json
import os
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

from db import Database

# ── Конфиг ────────────────────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get(
    "SPREADSHEET_ID", "1ri78JxboQ477L7nLOmXJupe2ALORwKqbh-jiKuAL8XE"
)
SCOPES = "https://www.googleapis.com/auth/spreadsheets"

# Цвета статусов вакансий (RGB 0-1)
STATUS_COLORS = {
    "applied":   {"red": 1.0,  "green": 0.95, "blue": 0.8},   # жёлтый
    "interview": {"red": 0.8,  "green": 0.95, "blue": 0.8},   # зелёный
    "offer":     {"red": 0.7,  "green": 0.9,  "blue": 1.0},   # синий
    "rejected":  {"red": 0.95, "green": 0.85, "blue": 0.85},  # красный
    "ignored":   {"red": 0.93, "green": 0.93, "blue": 0.93},  # серый
}
STATUS_RU = {
    "applied": "Ожидание", "interview": "Интервью",
    "offer": "Оффер", "rejected": "Отказ", "ignored": "Игнор",
}
FREELANCE_COLORS = {
    "sent":      {"red": 1.0,  "green": 0.95, "blue": 0.75},  # жёлтый
    "viewed":    {"red": 0.85, "green": 0.92, "blue": 1.0},   # синий
    "interview": {"red": 0.8,  "green": 0.95, "blue": 0.8},   # зелёный
    "won":       {"red": 0.7,  "green": 0.9,  "blue": 1.0},   # синий насыщ.
    "lost":      {"red": 0.95, "green": 0.85, "blue": 0.85},  # красный
}
FREELANCE_STATUS_RU = {
    "sent": "Отправлено", "viewed": "Просмотрено",
    "interview": "Интервью", "won": "Выиграно", "lost": "Отклонено",
}
HEADER_COLOR = {"red": 0.2, "green": 0.4, "blue": 0.7}

# ── JWT / Auth ─────────────────────────────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _key_file() -> Path | None:
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


def get_token() -> str:
    key_file = _key_file()
    if not key_file:
        raise RuntimeError("sheets_key.json не найден и GOOGLE_SERVICE_ACCOUNT_JSON не задан")
    key_data = json.loads(key_file.read_text())
    sa_email = key_data["client_email"]
    pk_pem = key_data["private_key"]
    now_ts = int(time.time())
    header  = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({
        "iss": sa_email, "scope": SCOPES,
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now_ts, "exp": now_ts + 3600,
    }).encode())
    signing_input = f"{header}.{payload}".encode()
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    pk = load_pem_private_key(pk_pem.encode(), password=None)
    sig = pk.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    jwt = f"{header}.{payload}.{_b64url(sig)}"
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt,
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]


# ── Sheets API helpers ─────────────────────────────────────────────────────────

def _api(token: str, method: str, url: str, body=None):
    data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8") if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        raise RuntimeError(f"Sheets API {method} {url}: {e.code} — {err[:300]}")


def get_sheet_ids(token: str) -> dict[str, int]:
    """Возвращает {имя_листа: sheetId}."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}?fields=sheets.properties"
    resp = _api(token, "GET", url)
    return {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in resp.get("sheets", [])
    }


def ensure_sheets(token: str, existing: dict[str, int], needed: list[str]) -> dict[str, int]:
    """Создаёт отсутствующие листы и возвращает обновлённый словарь {имя: sheetId}."""
    missing = [n for n in needed if n not in existing]
    if not missing:
        return existing
    print(f"  ➕ Создаю листы: {missing}...")
    reqs = [{"addSheet": {"properties": {"title": name}}} for name in missing]
    resp = _api(token, "POST",
                f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}:batchUpdate",
                {"requests": reqs})
    # Получаем свежий список
    return get_sheet_ids(token)


def clear_and_write(token: str, sheet_name: str, rows: list[list]):
    """Очищает ВЕСЬ лист (все столбцы) и записывает данные с A1."""
    # Clear ALL cells — имя листа без !A1, иначе старые столбцы остаются
    clear_range = urllib.parse.quote(sheet_name)
    _api(token, "POST",
         f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
         f"/values/{clear_range}:clear", {})
    if not rows:
        return
    # Write starting from A1
    write_range = urllib.parse.quote(f"{sheet_name}!A1")
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
           f"/values/{write_range}?valueInputOption=USER_ENTERED")
    _api(token, "PUT", url, {"values": rows})


def _reset_sheet_bg(sheet_id: int) -> dict:
    """Сбрасывает фон всего листа в белый перед новым форматированием."""
    return {
        "repeatCell": {
            "range": {"sheetId": sheet_id},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
            }},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }


def _unmerge_sheet(sheet_id: int) -> dict:
    """Снять все объединения ячеек (merges) на листе."""
    return {
        "unmergeCells": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0, "endRowIndex": 2000,
                "startColumnIndex": 0, "endColumnIndex": 30,
            }
        }
    }


def _freeze_header(sheet_id: int, frozen_rows: int = 1) -> dict:
    """Заморозить первые N строк, убрать заморозку столбцов."""
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {
                    "frozenRowCount": frozen_rows,
                    "frozenColumnCount": 0,
                }
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
        }
    }


def batch_format(token: str, requests: list):
    if not requests:
        return
    _api(token, "POST",
         f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}:batchUpdate",
         {"requests": requests})


def _color_row_request(sheet_id: int, row_idx: int, ncols: int, color: dict) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id, "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                "startColumnIndex": 0, "endColumnIndex": ncols,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": color}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }


def _header_request(sheet_id: int, ncols: int) -> list[dict]:
    """Жирный белый заголовок на тёмном фоне."""
    return [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                    "startColumnIndex": 0, "endColumnIndex": ncols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": HEADER_COLOR,
                        "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                        "horizontalAlignment": "CENTER",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]


def _autosize_request(sheet_id: int, ncols: int) -> dict:
    return {
        "autoResizeDimensions": {
            "dimensions": {
                "sheetId": sheet_id, "dimension": "COLUMNS",
                "startIndex": 0, "endIndex": ncols,
            }
        }
    }


def _set_column_width(sheet_id: int, col_idx: int, width_px: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id, "dimension": "COLUMNS",
                "startIndex": col_idx, "endIndex": col_idx + 1,
            },
            "properties": {"pixelSize": width_px},
            "fields": "pixelSize",
        }
    }


def _alternating_rows_request(sheet_id: int, start_row: int, end_row: int, ncols: int) -> list[dict]:
    """Чередующийся фон строк для лёгкого чтения (только для строк без статус-цвета)."""
    reqs = []
    light = {"red": 0.97, "green": 0.97, "blue": 0.97}
    for i in range(start_row, end_row, 2):
        reqs.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id, "startRowIndex": i, "endRowIndex": i + 1,
                    "startColumnIndex": 0, "endColumnIndex": ncols,
                },
                "cell": {"userEnteredFormat": {"backgroundColor": light}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        })
    return reqs


def _sort_request(sheet_id: int, col_idx: int, ascending: bool = False) -> dict:
    """Сортировка листа по одной колонке (по умолчанию убывание — новые сверху)."""
    return {
        "sortRange": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,  # пропускаем заголовок
                "startColumnIndex": 0,
            },
            "sortSpecs": [{
                "dimensionIndex": col_idx,
                "sortOrder": "ASCENDING" if ascending else "DESCENDING",
            }],
        }
    }


def _multi_sort_request(sheet_id: int, specs: list[tuple[int, bool]]) -> dict:
    """Мульти-колоночная сортировка. specs = [(col_idx, ascending), ...]"""
    return {
        "sortRange": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,  # пропускаем заголовок
                "startColumnIndex": 0,
            },
            "sortSpecs": [
                {
                    "dimensionIndex": col_idx,
                    "sortOrder": "ASCENDING" if asc else "DESCENDING",
                }
                for col_idx, asc in specs
            ],
        }
    }


def _add_pie_chart(sheet_id: int, anchor_row: int, anchor_col: int,
                   data_sheet_id: int, labels_col: int, values_col: int,
                   data_start_row: int, data_end_row: int, title: str) -> dict:
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "pieChart": {
                        "legendPosition": "RIGHT_LEGEND",
                        "series": {"sourceRange": {"sources": [{
                            "sheetId": data_sheet_id,
                            "startRowIndex": data_start_row, "endRowIndex": data_end_row,
                            "startColumnIndex": values_col, "endColumnIndex": values_col + 1,
                        }]}},
                        "domain": {"sourceRange": {"sources": [{
                            "sheetId": data_sheet_id,
                            "startRowIndex": data_start_row, "endRowIndex": data_end_row,
                            "startColumnIndex": labels_col, "endColumnIndex": labels_col + 1,
                        }]}},
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": anchor_col},
                        "widthPixels": 450, "heightPixels": 280,
                    }
                },
            }
        }
    }


def _add_line_chart(sheet_id: int, anchor_row: int, anchor_col: int,
                    data_sheet_id: int, x_col: int, y_cols: list[int],
                    y_labels: list[str], data_start_row: int, data_end_row: int,
                    title: str) -> dict:
    series = [
        {
            "series": {"sourceRange": {"sources": [{
                "sheetId": data_sheet_id,
                "startRowIndex": data_start_row, "endRowIndex": data_end_row,
                "startColumnIndex": c, "endColumnIndex": c + 1,
            }]}},
            "targetAxis": "LEFT_AXIS",
        }
        for c in y_cols
    ]
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "BOTTOM_LEGEND",
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "Дата"},
                            {"position": "LEFT_AXIS",   "title": "Кол-во"},
                        ],
                        "domains": [{"domain": {"sourceRange": {"sources": [{
                            "sheetId": data_sheet_id,
                            "startRowIndex": data_start_row, "endRowIndex": data_end_row,
                            "startColumnIndex": x_col, "endColumnIndex": x_col + 1,
                        }]}}}],
                        "series": series,
                        "headerCount": 0,
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {"sheetId": sheet_id, "rowIndex": anchor_row, "columnIndex": anchor_col},
                        "widthPixels": 550, "heightPixels": 300,
                    }
                },
            }
        }
    }


# ── Удаление существующих графиков ────────────────────────────────────────────

def delete_charts_on_sheet(token: str, sheet_id: int):
    """Удаляет все embedded charts с указанного листа."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}?fields=sheets(properties,charts)"
    resp = _api(token, "GET", url)
    reqs = []
    for sh in resp.get("sheets", []):
        if sh["properties"]["sheetId"] == sheet_id:
            for chart in sh.get("charts", []):
                reqs.append({"deleteEmbeddedObject": {"objectId": chart["chartId"]}})
    if reqs:
        batch_format(token, reqs)


# ── Листы ─────────────────────────────────────────────────────────────────────

def sync_vacancies(token: str, sheet_id: int, with_charts: bool):
    print("  📋 Вакансии...", end=" ", flush=True)
    with Database() as db:
        rows = db.get_vacancies(limit=2000)

    header = ["Дата", "Вакансия", "Компания", "Источник", "Статус",
              "Шаблон", "Пробелы скиллов", "Заметки", "URL"]
    data = [header]
    for r in rows:
        data.append([
            str(r.get("date") or ""),
            r.get("title") or "",
            r.get("company") or "",
            r.get("source") or "",
            STATUS_RU.get(r.get("status") or "", r.get("status") or ""),
            r.get("template_used") or "",
            r.get("skill_gaps") or "",
            r.get("notes") or "",
            r.get("url") or "",
        ])

    # Сначала снять merge — иначе headers D-I пишутся в объединённую ячейку
    batch_format(token, [_unmerge_sheet(sheet_id)])
    clear_and_write(token, "Вакансии", data)

    # Форматирование: freeze → сброс фона → заголовок → ширины → цвета → сортировка
    fmt_reqs = (
        [_freeze_header(sheet_id), _reset_sheet_bg(sheet_id)]
        + _header_request(sheet_id, len(header))
    )
    # Дата=80, Вакансия=250, Компания=160, Источник=90, Статус=90,
    # Шаблон=60, Пробелы=180, Заметки=200, URL=55
    widths = [80, 250, 160, 90, 90, 60, 180, 200, 55]
    for ci, w in enumerate(widths):
        fmt_reqs.append(_set_column_width(sheet_id, ci, w))
    # Цвет строк по статусу
    for i, r in enumerate(rows, start=1):
        color = STATUS_COLORS.get(r.get("status") or "", None)
        if color:
            fmt_reqs.append(_color_row_request(sheet_id, i, len(header), color))
    # Сортировка: новые вверху
    # Сортировка: дата ↓, компания ↑, источник ↑
    fmt_reqs.append(_multi_sort_request(sheet_id, [(0, False), (2, True), (3, True)]))
    batch_format(token, fmt_reqs)

    # Графики
    if with_charts and len(rows) > 0:
        delete_charts_on_sheet(token, sheet_id)
        # Сводная таблица статусов на вспомогательной зоне (col K, L начиная с row 2)
        status_counts = Counter(r.get("status") for r in rows)
        stat_rows = [["Статус", "Кол-во"]] + [
            [STATUS_RU.get(k, k), v] for k, v in sorted(status_counts.items())
        ]
        # Записываем в K:L
        range_kl = urllib.parse.quote("Вакансии!K1")
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
               f"/values/{range_kl}?valueInputOption=USER_ENTERED")
        _api(token, "PUT", url, {"values": stat_rows})

        pie_req = _add_pie_chart(
            sheet_id=sheet_id, anchor_row=1, anchor_col=10,
            data_sheet_id=sheet_id, labels_col=10, values_col=11,
            data_start_row=1, data_end_row=1 + len(stat_rows),
            title="Распределение по статусам",
        )
        batch_format(token, [pie_req])

    print(f"{len(rows)} строк ✓")


def sync_freelance(token: str, sheet_id: int, with_charts: bool):
    print("  💼 Фриланс...", end=" ", flush=True)
    with Database() as db:
        rows = db.get_freelance(limit=1000)

    header = ["Дата", "Платформа", "Проект", "Клиент", "Бюджет ($)",
              "Ставка ($)", "Connects", "Шаблон", "Статус", "Заметки", "URL"]
    data = [header]
    for r in rows:
        data.append([
            str(r.get("date") or ""),
            r.get("platform") or "",
            r.get("project_title") or "",
            r.get("client") or "",
            str(r.get("budget") or ""),
            str(r.get("our_rate") or ""),
            str(r.get("connects_spent") or "0"),
            (r.get("template_used") or "").replace("шаблон ", "").replace("Шаблон ", ""),
            FREELANCE_STATUS_RU.get(r.get("status") or "", r.get("status") or ""),
            r.get("comment") or "",
            r.get("url") or "",
        ])

    clear_and_write(token, "Фриланс", data)

    fmt_reqs = (
        [_unmerge_sheet(sheet_id), _freeze_header(sheet_id), _reset_sheet_bg(sheet_id)]
        + _header_request(sheet_id, len(header))
    )
    # Дата=80, Платформа=90, Проект=280, Клиент=130, Бюджет=75, Ставка=65,
    # Connects=75, Шаблон=70, Статус=90, Заметки=200, URL=60
    fl_widths = [80, 90, 280, 130, 75, 65, 75, 70, 90, 200, 60]
    for ci, w in enumerate(fl_widths):
        fmt_reqs.append(_set_column_width(sheet_id, ci, w))
    for i, r in enumerate(rows, start=1):
        color = FREELANCE_COLORS.get(r.get("status") or "", None)
        if color:
            fmt_reqs.append(_color_row_request(sheet_id, i, len(header), color))
    fmt_reqs.append(_sort_request(sheet_id, col_idx=0, ascending=False))
    batch_format(token, fmt_reqs)

    if with_charts and len(rows) > 0:
        delete_charts_on_sheet(token, sheet_id)
        plat_counts = Counter(r.get("platform") for r in rows)
        plat_rows = [["Платформа", "Откликов"]] + sorted(plat_counts.items(), key=lambda x: -x[1])
        range_m = urllib.parse.quote("Фриланс!M1")
        url = (f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
               f"/values/{range_m}?valueInputOption=USER_ENTERED")
        _api(token, "PUT", url, {"values": plat_rows})
        # bar chart через BAR type
        bar_req = {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Отклики по платформам",
                        "basicChart": {
                            "chartType": "BAR",
                            "legendPosition": "NO_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Откликов"},
                                {"position": "LEFT_AXIS",   "title": "Платформа"},
                            ],
                            "domains": [{"domain": {"sourceRange": {"sources": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 0, "endRowIndex": len(plat_rows),
                                "startColumnIndex": 12, "endColumnIndex": 13,
                            }]}}}],
                            "series": [{"series": {"sourceRange": {"sources": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 0, "endRowIndex": len(plat_rows),
                                "startColumnIndex": 13, "endColumnIndex": 14,
                            }]}}, "targetAxis": "BOTTOM_AXIS"}],
                            "headerCount": 1,
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {"sheetId": sheet_id, "rowIndex": 1, "columnIndex": 12},
                            "widthPixels": 400, "heightPixels": 260,
                        }
                    },
                }
            }
        }
        batch_format(token, [bar_req])

    print(f"{len(rows)} строк ✓")


def sync_stats(token: str, sheet_id: int, with_charts: bool):
    print("  📊 Статистика...", end=" ", flush=True)
    with Database() as db:
        rows = db.get_daily_stats_rows(days=60)

    # Fallback: если daily_stats пуста — считаем из таблицы vacancies по дате отклика
    if not rows:
        from collections import defaultdict
        with Database() as db:
            vacs = db.get_vacancies(limit=5000)
        by_date: dict = defaultdict(lambda: {"applied": 0, "viewed": 0,
                                              "interview": 0, "offer": 0, "rejected": 0})
        for v in vacs:
            d = str(v.get("date") or "")[:10]
            if not d:
                continue
            s = v.get("status", "")
            by_date[d]["applied"] += 1
            if s == "interview":   by_date[d]["interview"] += 1
            elif s == "offer":     by_date[d]["offer"] += 1
            elif s == "rejected":  by_date[d]["rejected"] += 1
        rows = [
            {"stat_date": d,
             "applied_count": v["applied"], "viewed_count": v["viewed"],
             "interview_count": v["interview"], "offer_count": v["offer"],
             "rejected_count": v["rejected"]}
            for d, v in sorted(by_date.items(), reverse=True)[:60]
        ]
        print(f"(fallback из vacancies: {len(rows)} дней) ", end="", flush=True)

    header = ["Дата", "Подано откликов", "Просмотрено", "Интервью", "Офферов", "Отказов"]
    data = [header]
    for r in rows:
        data.append([
            str(r.get("stat_date") or r.get("date") or ""),
            str(r.get("applied_count") or r.get("applied") or 0),
            str(r.get("viewed_count") or r.get("viewed") or 0),
            str(r.get("interview_count") or r.get("interview") or 0),
            str(r.get("offer_count") or r.get("offer") or 0),
            str(r.get("rejected_count") or r.get("rejected") or 0),
        ])

    clear_and_write(token, "Статистика", data)
    fmt_reqs = [_reset_sheet_bg(sheet_id)] + _header_request(sheet_id, len(header))
    # Дата=90, остальные по 80
    fmt_reqs.append(_set_column_width(sheet_id, 0, 90))
    for ci in range(1, len(header)):
        fmt_reqs.append(_set_column_width(sheet_id, ci, 80))
    # Чередующийся фон для удобства чтения
    fmt_reqs += _alternating_rows_request(sheet_id, 1, len(data), len(header))
    fmt_reqs.append(_sort_request(sheet_id, col_idx=0, ascending=False))
    batch_format(token, fmt_reqs)

    if with_charts and len(rows) > 1:
        delete_charts_on_sheet(token, sheet_id)
        line_req = _add_line_chart(
            sheet_id=sheet_id, anchor_row=1, anchor_col=7,
            data_sheet_id=sheet_id, x_col=0, y_cols=[1, 3],
            y_labels=["Подано", "Интервью"],
            data_start_row=0, data_end_row=len(data),
            title="Активность за 60 дней",
        )
        batch_format(token, [line_req])

    print(f"{len(rows)} строк ✓")



# ─────────────────────────────────────────────────────────────────────
# Skill Gap — детальный анализ с категориями и проектами
# ─────────────────────────────────────────────────────────────────────

# Карта: навык → (категория, закрывается проектом, статус)
# Статус: ✅ Закрыто / 📍 Запланировано / ❌ Нет проекта / — (noise)
SKILL_GAP_META: dict[str, tuple[str, str, str]] = {
    # ── Qt / QML ──
    "Qt Advanced (signal/slot internals)": ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "QML performance optimization":        ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "Qt 6 migration":                      ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "Qt/QML industrial UI":                ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "Qt advanced":                         ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "Qt 6 advanced":                       ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "QML performance profiling":           ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "QML продвинутый уровень":             ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "QML (есть Qt — нужно добавить QML мини-проект)": ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "QML":                                 ("Qt/QML", "qml_system_monitor", "✅ Закрыто"),
    "ЗАКРЫТА 28.06 — Qt5/6 advanced":     ("Qt/QML", "Вакансия закрыта", "✅ Закрыто"),
    "cross-platform packaging":            ("Qt/QML", "#8 Qt Dashboard", "📍 Запланировано"),
    "Android (Qt on Android)":             ("Android/Mobile", "Нужен Android-стек", "❌ Нет проекта"),
    # ── Embedded / Hardware ──
    "RTOS платформа конкретной компании":  ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "hardware debugging (JTAG)":           ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "bare-metal разработка":               ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "STM32 HAL/CubeMX продвинутый":        ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "RTOS на MCU":                         ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "аппаратная отладка JTAG/SWD":         ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "PLC интеграция":                      ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "промышленные стандарты IEC 61131":    ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "EtherCAT мастер/слейв":              ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "Motion Control алгоритмы":            ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "realtime Linux (PREEMPT-RT)":         ("Embedded", "#14 eBPF Monitor", "📍 Запланировано"),
    "CAN/LIN протоколы":                   ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "Bootloader разработка":               ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "RTOS (FreeRTOS/Zephyr) продвинутый":  ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "Embedded Linux (Yocto/Buildroot)":    ("Embedded", "Нужен реальный Linux SBC", "❌ Нет проекта"),
    "Linux BSP (Yocto/Buildroot)":         ("Embedded", "Нужен реальный Linux SBC", "❌ Нет проекта"),
    "Device Tree / DTS":                   ("Embedded", "Нужен реальный Linux SBC", "❌ Нет проекта"),
    "Device Tree Source":                  ("Embedded", "Нужен реальный Linux SBC", "❌ Нет проекта"),
    "Device Tree":                         ("Embedded", "Нужен реальный Linux SBC", "❌ Нет проекта"),
    "kernel modules":                      ("Embedded", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "U-Boot":                              ("Embedded", "Нужен реальный Linux SBC", "❌ Нет проекта"),
    "ARM SoC firmware bare-metal":         ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "PCI/PCIe":                            ("Embedded", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "UEFI/EDK2":                           ("Embedded", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "отладка JTAG/TRACE32":               ("Embedded", "Нужно физическое железо", "❌ Нет проекта"),
    "Embedded RTOS (FreeRTOS)":            ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "I2C/SPI/CAN/USB":                    ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "ARM Cortex-M":                        ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "принтерное железо/периферия":         ("Embedded", "Узкоспециализировано", "❌ Нет проекта"),
    "RTOS (VxWorks/LynxOS)":              ("Embedded", "Проприетарный RTOS", "❌ Нет проекта"),
    "промышленные протоколы (Modbus/OPC-UA)":("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "SCADA системы":                       ("Embedded", "Узкоспециализировано", "❌ Нет проекта"),
    "TCP/IP bare metal":                   ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "real-time планировщик":               ("Embedded", "#13 MCU Simulator", "📍 Запланировано"),
    "FPGA взаимодействие":                 ("Embedded", "#18 HFT Engine (концепции)", "📍 Запланировано"),
    "Rockchip/Jetson платформы":           ("Embedded", "Нужна плата", "❌ Нет проекта"),
    "Android HAL":                         ("Android/Mobile", "Нужен Android NDK", "❌ Нет проекта"),
    "GStreamer медиапайплайн":             ("Multimedia", "Нужна медиа-специализация", "❌ Нет проекта"),
    "GStreamer/видеопайплайн":             ("Multimedia", "Нужна медиа-специализация", "❌ Нет проекта"),
    "NPU/GPU ускорение":                   ("ML/AI", "#12 ML + ONNX", "📍 Запланировано"),
    # ── Highload / Data ──
    "highload C++ (10M+ RPS)":             ("Highload", "#7 C++20 Showcase", "📍 Запланировано"),
    "распределённые СУБД (YDB/ClickHouse)":("Highload", "#16 ClickHouse Analytics", "📍 Запланировано"),
    "MapReduce/Spark":                     ("Highload", "#16 ClickHouse Analytics", "📍 Запланировано"),
    "движки СУБД (B-Tree/LSM)":            ("Highload", "#16 ClickHouse Analytics", "📍 Запланировано"),
    "WAL / MVCC":                          ("Highload", "#16 ClickHouse Analytics", "📍 Запланировано"),
    "query optimizer":                     ("Highload", "#16 ClickHouse Analytics", "📍 Запланировано"),
    "шардирование":                        ("Highload", "#16 ClickHouse Analytics", "📍 Запланировано"),
    "Распределённые БД (YDB/ClickHouse)":  ("Highload", "#16 ClickHouse Analytics", "📍 Запланировано"),
    "highload backend C++":                ("Highload", "#7 C++20 Showcase", "📍 Запланировано"),
    "Apache Kafka C++":                    ("Highload", "#16 ClickHouse Analytics", "📍 Запланировано"),
    "highload геосервисы":                 ("Highload", "#7 C++20 Showcase", "📍 Запланировано"),
    "highload inference pipeline":         ("ML/AI", "#12 ML + ONNX", "📍 Запланировано"),
    "высокая нагрузка (>10k rps)":         ("Highload", "#7 C++20 Showcase", "📍 Запланировано"),
    "микросервисная архитектура":          ("Highload", "#10 gRPC Microservice", "📍 Запланировано"),
    # ── Low-latency / Finance ──
    "low-latency C++ (<1мкс)":             ("Low-latency", "#18 HFT Engine", "📍 Запланировано"),
    "финансовые алгоритмы (quant)":        ("Low-latency", "#18 HFT Engine", "📍 Запланировано"),
    "FPGA/ASIC основы":                    ("Low-latency", "#18 HFT Engine (концепции)", "📍 Запланировано"),
    "банковские протоколы (SWIFT/FIX)":    ("Low-latency", "#18 HFT Engine", "📍 Запланировано"),
    "Oracle интеграция":                   ("Low-latency", "Узкоспециализировано", "❌ Нет проекта"),
    "финансовая математика":               ("Low-latency", "#18 HFT Engine", "📍 Запланировано"),
    "DSP сигналы/радар":                   ("Low-latency", "Узкоспециализировано РЛС", "❌ Нет проекта"),
    # ── Network / Systems ──
    "DPDK/RDMA":                           ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "eBPF":                                ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "сетевая коммутация P4":               ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "DPDK (Data Plane Development Kit)":   ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "SR-IOV":                              ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "eBPF/XDP":                            ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "Linux kernel internals":              ("Network", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "системные вызовы / eBPF":             ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "сетевые протоколы L2-L4":             ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "виртуализация сети":                  ("Network", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "Сетевое программирование ядра (DPDK/eBPF/kernel bypass)": ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "C++ сетевой стек":                    ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "сетевые протоколы low-level":         ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    "Windows VPN стек (WFP/TDI)":          ("Security", "#15 Kernel Driver", "📍 Запланировано"),
    "Windows сетевые драйверы":            ("Security", "#15 Kernel Driver", "📍 Запланировано"),
    "Сетевые протоколы RDP/VNC/SPICE":     ("Network", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "виртуализация (KVM/Hyper-V)":         ("Network", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "VDI архитектура":                     ("Network", "Узкоспециализировано", "❌ Нет проекта"),
    "блочные устройства Linux":            ("Network", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "NVMe/iSCSI":                          ("Network", "#15 Kernel Driver LKM", "📍 Запланировано"),
    "профилирование perf/flamegraph":      ("Network", "#14 eBPF Monitor", "📍 Запланировано"),
    # ── ML / AI ──
    "CUDA/GPU программирование":           ("ML/AI", "#12 ML + ONNX", "📍 Запланировано"),
    "ML inference C++":                    ("ML/AI", "#12 ML + ONNX", "📍 Запланировано"),
    "ML/LLM inference":                    ("ML/AI", "#12 ML + ONNX", "📍 Запланировано"),
    "трансформеры":                        ("ML/AI", "#12 ML + ONNX", "📍 Запланировано"),
    "нейросети на C++":                    ("ML/AI", "#12 ML + ONNX", "📍 Запланировано"),
    # ── Security / DLP ──
    "DLP системы (архитектура)":           ("Security", "WinAPI Showcase", "✅ Закрыто"),
    "перехват сетевого трафика":           ("Security", "WinAPI Showcase", "✅ Закрыто"),
    "Windows kernel hooks":                ("Security", "WinAPI Showcase", "✅ Закрыто"),
    "DevSecOps практики":                  ("Security", "#10 gRPC + CI", "📍 Запланировано"),
    "SAST/DAST инструменты":               ("Security", "#10 gRPC + CI", "📍 Запланировано"),
    "аудит безопасности кода":             ("Security", "#10 gRPC + CI", "📍 Запланировано"),
    "криптография (TLS 1.3/WireGuard)":    ("Security", "#14 eBPF Monitor", "📍 Запланировано"),
    # ── Multimedia / Media ──
    "WebRTC/RTP стек":                     ("Multimedia", "#17 WebRTC Signaling", "📍 Запланировано"),
    "WebRTC":                              ("Multimedia", "#17 WebRTC Signaling", "📍 Запланировано"),
    "медиасервер":                         ("Multimedia", "#17 WebRTC Signaling", "📍 Запланировано"),
    "RTP/RTCP":                            ("Multimedia", "#17 WebRTC Signaling", "📍 Запланировано"),
    "низкая задержка аудио/видео":         ("Multimedia", "#17 WebRTC Signaling", "📍 Запланировано"),
    "медиа-пайплайн":                      ("Multimedia", "Нужна медиа-специализация", "❌ Нет проекта"),
    "Мультимедиа кодеки":                  ("Multimedia", "Нужна медиа-специализация", "❌ Нет проекта"),
    # ── Android / Mobile ──
    "Android NDK/JNI":                     ("Android/Mobile", "Нужен Android NDK", "❌ Нет проекта"),
    "мобильная разработка C++":            ("Android/Mobile", "Нужен Android NDK", "❌ Нет проекта"),
    "Android NDK":                         ("Android/Mobile", "Нужен Android NDK", "❌ Нет проекта"),
    "JNI":                                 ("Android/Mobile", "Нужен Android NDK", "❌ Нет проекта"),
    "WebRTC Android":                      ("Android/Mobile", "Нужен Android NDK", "❌ Нет проекта"),
    "Android build system (Gradle+CMake)": ("Android/Mobile", "Нужен Android NDK", "❌ Нет проекта"),
    # ── CAD / 3D ──
    "nanoCAD/КОМПАС API":                  ("CAD/3D", "Узкоспециализировано", "❌ Нет проекта"),
    "ACIS геометрическое ядро":            ("CAD/3D", "Узкоспециализировано", "❌ Нет проекта"),
    "OpenGL 3D рендеринг":                 ("CAD/3D", "Узкоспециализировано", "❌ Нет проекта"),
    "3D геометрия (ACIS/STEP/IGES)":       ("CAD/3D", "Узкоспециализировано", "❌ Нет проекта"),
    "OpenGL/Vulkan рендеринг":             ("CAD/3D", "Узкоспециализировано", "❌ Нет проекта"),
    "CAD ядра":                            ("CAD/3D", "Узкоспециализировано", "❌ Нет проекта"),
    "вычислительная геометрия":            ("CAD/3D", "Узкоспециализировано", "❌ Нет проекта"),
    # ── Telecom / Avionics ──
    "телеком стек (SIP/RTP)":              ("Telecom", "Узкоспециализировано", "❌ Нет проекта"),
    "IMS архитектура":                     ("Telecom", "Узкоспециализировано", "❌ Нет проекта"),
    "VoIP разработка":                     ("Telecom", "Узкоспециализировано", "❌ Нет проекта"),
    "RTOS networking stack":               ("Telecom", "#13 MCU Simulator", "📍 Запланировано"),
    "телеком стек (LTE/5G)":              ("Telecom", "Узкоспециализировано", "❌ Нет проекта"),
    "3GPP протоколы":                      ("Telecom", "Узкоспециализировано", "❌ Нет проекта"),
    "RAN/Core Network архитектура":        ("Telecom", "Узкоспециализировано", "❌ Нет проекта"),
    "VK CI/CD pipeline":                   ("Soft/Org", "VK-специфично", "❌ Нет проекта"),
    "avionic стандарты (DO-178C)":         ("Avionics", "Узкоспециализировано", "❌ Нет проекта"),
    "ARINC 429/664":                       ("Avionics", "MIL-1553 → близкая область", "📍 Запланировано"),
    "MAVLink протокол":                    ("Avionics", "Нужен дрон проект", "❌ Нет проекта"),
    "авиационные стандарты":               ("Avionics", "Узкоспециализировано", "❌ Нет проекта"),
    "модели данных БПЛА":                  ("Avionics", "Нужен дрон проект", "❌ Нет проекта"),
    "специфика РЛС — нужно изучить вакансию детальнее": ("Avionics", "РЛС-специфично", "❌ Нет проекта"),
    # ── Geo / Navigation ──
    "геопространственные алгоритмы":       ("Geo", "Узкоспециализировано", "❌ Нет проекта"),
    "навигационные SDK":                   ("Geo", "Узкоспециализировано", "❌ Нет проекта"),
    "Алгоритмы графов (Dijkstra/A*/CH)":  ("Geo", "Узкоспециализировано", "❌ Нет проекта"),
    "картографические данные":             ("Geo", "Узкоспециализировано", "❌ Нет проекта"),
    "геоалгоритмы":                        ("Geo", "Узкоспециализировано", "❌ Нет проекта"),
    "OSRM":                                ("Geo", "Узкоспециализировано", "❌ Нет проекта"),
    # ── Platform / Specific ──
    "Sailfish OS / Aurora SDK":            ("Platform", "Aurora-специфично", "❌ Нет проекта"),
    "RPM-пакетирование Aurora":            ("Platform", "Aurora-специфично", "❌ Нет проекта"),
    "Go (Golang) базовый":                 ("Platform", "Не C++ стек", "❌ Нет проекта"),
    "CGo интеграция":                      ("Platform", "Не C++ стек", "❌ Нет проекта"),
    # ── Tooling / DevOps ──
    "CMake advanced (мультиплатформ. конфиги)": ("Tooling", "#7 C++20 Showcase", "📍 Запланировано"),
    "SVN":                                 ("Tooling", "Устаревший инструмент", "❌ Нет проекта"),
    "системы сборки DevSecOps":            ("Tooling", "#10 gRPC + CI", "📍 Запланировано"),
    "статический анализ (PVS/Coverity)":   ("Tooling", "#10 gRPC + CI", "📍 Запланировано"),
    "CI/CD (GitLab CI/Jenkins)":           ("Tooling", "#10 gRPC + CI", "📍 Запланировано"),
    # ── Soft / Org ──
    "техническое лидерство":              ("Soft/Org", "Рост в компании", "❌ Нет проекта"),
    "опыт Team Lead (1+ год)":             ("Soft/Org", "Рост в компании", "❌ Нет проекта"),
    "планирование спринтов (Jira)":        ("Soft/Org", "Рост в компании", "❌ Нет проекта"),
    "архитектурный опыт large codebase":   ("Soft/Org", "Рост в компании", "❌ Нет проекта"),
    "code review / mentoring":             ("Soft/Org", "Рост в компании", "❌ Нет проекта"),
    # ── В резюме (уже закрыто) ──
    "D-Bus (Linux IPC)":                   ("✅ В резюме", "dbus_service", "✅ Закрыто"),
    "Linux system programming":            ("✅ В резюме", "dbus_service + dbus", "✅ Закрыто"),
    "многопоточность (не указана в резюме)":("✅ В резюме", "Добавить в резюме", "✅ Закрыто"),
    "lock-free структуры":                 ("Highload", "#7 C++20 Showcase", "📍 Запланировано"),
}

CATEGORY_ORDER = [
    "Qt/QML", "Embedded", "Highload", "Low-latency", "Network",
    "Security", "ML/AI", "Multimedia", "Tooling", "Soft/Org",
    "Android/Mobile", "Telecom", "Avionics", "CAD/3D", "Geo",
    "Platform", "✅ В резюме",
]



def _delete_bandings_and_filters(token: str, sheet_id: int) -> None:
    """Удалить все BandedRange (Таблица1) и фильтры на листе."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    reqs = []
    for sheet in data.get("sheets", []):
        if sheet["properties"]["sheetId"] == sheet_id:
            for br in sheet.get("bandedRanges", []):
                reqs.append({"deleteBanding": {"bandedRangeId": br["bandedRangeId"]}})
            break
    reqs.append({"clearBasicFilter": {"sheetId": sheet_id}})
    if reqs:
        batch_format(token, reqs)

def sync_skill_gap_rich(token: str, sheet_id: int):
    """Skill Gap tab — детальный анализ с категориями, частотой и проектами."""
    print("  📊 Skill Gap...", end=" ", flush=True)
    with Database() as db:
        raw = db.get_skill_gaps(limit=1000)

    counter: Counter = Counter()
    for r in raw:
        gaps = r.get("skill_gaps") or ""
        for g in gaps.split(","):
            g = g.strip()
            if g and g not in ("domain expertise компании", "внутренние инструменты и процессы"):
                counter[g] += 1

    # Сборка строк с мета-данными
    STATUS_SORT = {"📍 Запланировано": 0, "❌ Нет проекта": 1, "✅ Закрыто": 2, "—": 3}
    header = ["Категория", "Навык / Пробел", "Упоминаний", "Приоритет", "Закрывается проектом", "Статус"]
    rows_by_cat: dict[str, list] = {}
    for skill, cnt in counter.most_common(200):
        meta = SKILL_GAP_META.get(skill, ("Прочее", "—", "❌ Нет проекта"))
        cat, project, status = meta
        priority = "🔴 Критический" if cnt >= 4 else ("🟡 Средний" if cnt >= 2 else "🟢 Низкий")
        entry = [cat, skill, cnt, priority, project, status]
        rows_by_cat.setdefault(cat, []).append(entry)

    # Сортировка: внутри категории → статус (📍→❌→✅) → частота desc
    data = [header]
    for cat in CATEGORY_ORDER + sorted(set(rows_by_cat) - set(CATEGORY_ORDER)):
        if cat not in rows_by_cat:
            continue
        cat_rows = sorted(rows_by_cat[cat],
                          key=lambda x: (STATUS_SORT.get(x[5], 9), -x[2]))
        data.extend(cat_rows)

    _delete_bandings_and_filters(token, sheet_id)
    batch_format(token, [_unmerge_sheet(sheet_id)])
    clear_and_write(token, "Skill Gap", data)

    fmt_reqs = (
        [_freeze_header(sheet_id), _reset_sheet_bg(sheet_id)]
        + _header_request(sheet_id, len(header))
    )
    # Ширины колонок: Категория, Навык, Кол-во, Приоритет, Проект, Статус
    for ci, w in enumerate([110, 280, 90, 110, 200, 130]):
        fmt_reqs.append(_set_column_width(sheet_id, ci, w))

    # Цвет строк по приоритету
    # Цвет = по Статусу (col 5), не по приоритету — легче читать
    STATUS_ROW_COLORS = {
        "📍 Запланировано": {"red": 0.90, "green": 0.96, "blue": 1.0},   # голубой
        "❌ Нет проекта":   {"red": 1.0,  "green": 0.93, "blue": 0.88},  # персиковый
        "✅ Закрыто":       {"red": 0.93, "green": 0.93, "blue": 0.93},  # серый
    }
    for i, row in enumerate(data[1:], start=1):
        status_val = row[5] if len(row) > 5 else ""
        color = STATUS_ROW_COLORS.get(status_val, None)
        if color:
            fmt_reqs.append(_color_row_request(sheet_id, i, len(header), color))

    batch_format(token, fmt_reqs)
    print(f"{len(data)-1} строк ✓")

def sync_skill_gap(token: str, sheet_id: int, with_charts: bool):
    print("  🔍 Skill Gap...", end=" ", flush=True)
    with Database() as db:
        raw = db.get_skill_gaps(limit=1000)

    # Агрегация
    counter: Counter = Counter()
    for r in raw:
        gaps = r.get("skill_gaps") or ""
        for g in gaps.split(","):
            g = g.strip()
            if g:
                counter[g] += 1

    header = ["Навык", "Упоминаний", "Приоритет"]
    data = [header]
    for skill, cnt in counter.most_common(50):
        priority = "🔴 Высокий" if cnt >= 5 else ("🟡 Средний" if cnt >= 2 else "🟢 Низкий")
        data.append([skill, cnt, priority])

    clear_and_write(token, "Топ Навыков", data)
    fmt_reqs = [_reset_sheet_bg(sheet_id)] + _header_request(sheet_id, 3) + [_autosize_request(sheet_id, 3)]
    # Цвет строк по приоритету
    for i, row in enumerate(data[1:], start=1):
        pri = row[2] if len(row) > 2 else ""
        if "Высокий" in pri:
            color = {"red": 1.0, "green": 0.87, "blue": 0.87}
        elif "Средний" in pri:
            color = {"red": 1.0, "green": 0.97, "blue": 0.8}
        else:
            color = {"red": 0.88, "green": 0.97, "blue": 0.88}
        fmt_reqs.append(_color_row_request(sheet_id, i, 3, color))
    batch_format(token, fmt_reqs)
    print(f"{len(counter)} навыков ✓")


def sync_dashboard(token: str, sheet_id: int):
    print("  🏠 Dashboard...", end=" ", flush=True)
    with Database() as db:
        summary = db.get_vacancy_summary(stale_days=7)
        stats   = db.get_stats(days=30)
        fl_rows = db.get_freelance(limit=500)

    today = date.today().strftime("%d.%m.%Y")
    week_ago = (date.today() - timedelta(days=7)).strftime("%d.%m.%Y")

    fl_active = sum(1 for r in fl_rows if r.get("status") not in ("lost", "ignored"))
    fl_won    = sum(1 for r in fl_rows if r.get("status") == "won")
    fl_total  = len(fl_rows)
    fl_rate   = f"{fl_won/fl_total*100:.0f}%" if fl_total else "0%"

    v_week = stats.get("by_date", {})
    applied_week = sum(v_week.get(str(date.today() - timedelta(days=i)), {}).get("applied", 0)
                       for i in range(7))

    rows = [
        ["📊 ДАШБОРД — Поиск работы", today],
        [""],
        ["🗂️ ВАКАНСИИ", ""],
        ["Всего откликов",      summary.get("total", 0)],
        ["Ожидают ответа",      summary.get("waiting", 0)],
        ["Устаревших (>7 дн.)", summary.get("stale", 0)],
        ["Интервью",            summary.get("interview", 0)],
        ["Офферов",             summary.get("offer", 0)],
        ["Отказов",             summary.get("rejected", 0)],
        [""],
        ["💼 ФРИЛАНС (всего)", ""],
        ["Всего откликов",      fl_total],
        ["Активных",           fl_active],
        ["Выиграно",           fl_won],
        ["Конверсия",          fl_rate],
        [""],
        ["📈 АКТИВНОСТЬ (30 дн.)", ""],
        ["Подано за 30 дней",   stats.get("total_period", 0)],
        ["Подано за 7 дней",    applied_week],
        [""],
        ["🕐 Обновлено", today],
    ]

    clear_and_write(token, "Dashboard", rows)

    # Форматирование заголовков секций
    fmt_reqs = [
        _reset_sheet_bg(sheet_id),
        _set_column_width(sheet_id, 0, 220),
        _set_column_width(sheet_id, 1, 120),
    ]
    section_rows = [0, 2, 10, 16]
    for r_idx in section_rows:
        fmt_reqs.append({
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": r_idx, "endRowIndex": r_idx + 1,
                          "startColumnIndex": 0, "endColumnIndex": 2},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True, "fontSize": 11},
                    "backgroundColor": {"red": 0.93, "green": 0.93, "blue": 0.93},
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })
    batch_format(token, fmt_reqs)
    print("✓")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Зеркалирование PG → Google Sheets")
    parser.add_argument("--sheet",     default=None, help="Только этот лист (имя)")
    parser.add_argument("--no-charts", action="store_true", help="Без графиков")
    args = parser.parse_args()

    with_charts = not args.no_charts
    t0 = time.time()
    print("🔄 Синхронизация PostgreSQL → Google Sheets...")

    print("  🔐 Auth...", end=" ", flush=True)
    try:
        token = get_token()
        print("✓")
    except Exception as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        sys.exit(1)

    print("  📑 Получаю список листов...", end=" ", flush=True)
    try:
        sheet_ids = get_sheet_ids(token)
        print(f"{list(sheet_ids.keys())}")
    except Exception as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        sys.exit(1)

    # Создаём отсутствующие листы автоматически
    needed = ["Вакансии", "Фриланс", "Статистика", "Топ Навыков", "Dashboard", "Skill Gap"]
    if not args.sheet or args.sheet in needed:
        sheet_ids = ensure_sheets(token, sheet_ids, needed)

    def run(name: str, fn):
        if args.sheet and args.sheet != name:
            return
        sid = sheet_ids.get(name)
        if sid is None:
            print(f"  ⚠️  Лист '{name}' не найден — пропущен")
            return
        try:
            fn(token, sid)
        except Exception as e:
            print(f"  ❌ {name}: {e}", file=sys.stderr)

    run("Вакансии",  lambda t, s: sync_vacancies(t, s, with_charts))
    run("Фриланс",   lambda t, s: sync_freelance(t, s, with_charts))
    run("Статистика", lambda t, s: sync_stats(t, s, with_charts))
    run("Топ Навыков", lambda t, s: sync_skill_gap(t, s, with_charts))
    run("Skill Gap",  lambda t, s: sync_skill_gap_rich(t, s))
    run("Dashboard",  lambda t, s: sync_dashboard(t, s))

    elapsed = time.time() - t0
    print(f"\n✅ Готово за {elapsed:.1f} сек")
    print(f"   https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}")


if __name__ == "__main__":
    main()
