"""
app/routers/analytics.py — OLAP аналитика из ClickHouse.

GET /analytics/top-companies?days=30
GET /analytics/conversion?source=hh.kz
GET /analytics/skill-trends?months=3
GET /analytics/salary-by-stack

Примечание: ClickHouse — опциональная зависимость.
При CLICKHOUSE_URL="" все эндпоинты возвращают 503.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth import verify_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ── Pydantic-схемы ─────────────────────────────────────────────────────────

class TopCompanyItem(BaseModel):
    company: str
    count:   int


class ConversionItem(BaseModel):
    source:    str
    applied:   int
    interview: int
    offer:     int
    rejected:  int
    conv_pct:  float


class SkillTrendItem(BaseModel):
    skill:      str
    total:      int
    prev_month: int
    curr_month: int
    trend:      str       # "up" | "down" | "stable"


class SalaryStackItem(BaseModel):
    skill:         str
    avg_salary:    int
    vacancy_count: int


# ── Зависимость: ClickHouse клиент ────────────────────────────────────────

def _get_ch_client():
    """FastAPI dependency — возвращает CH клиент или поднимает 503."""
    try:
        from db.clickhouse_writer import ClickHouseWriter, ClickHouseError  # noqa: PLC0415
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="clickhouse-connect не установлен. Добавьте в requirements.txt",
        )

    writer = ClickHouseWriter(graceful=False)
    if writer._client is None:
        raise HTTPException(
            status_code=503,
            detail="ClickHouse недоступен. Проверьте CLICKHOUSE_URL.",
        )
    return writer._client


# ── Эндпоинты ─────────────────────────────────────────────────────────────

@router.get("/top-companies", response_model=list[TopCompanyItem])
async def get_top_companies(
    days: int = Query(30, ge=1, le=365, description="За сколько дней"),
    _:    str = Depends(verify_token),
):
    """
    Топ компаний по количеству вакансий за последние N дней (из ClickHouse).

    Используется для анализа рынка: какие компании активно нанимают.
    """
    from automation.analytics import top_companies, AnalyticsError  # noqa: PLC0415
    try:
        client = _get_ch_client()
        data = top_companies(client, days=days)
        return [TopCompanyItem(**row) for row in data]
    except HTTPException:
        raise
    except AnalyticsError as exc:
        logger.error("/analytics/top-companies: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/conversion", response_model=list[ConversionItem])
async def get_conversion(
    source: Optional[str] = Query(None, description="Фильтр по источнику (hh.kz, LinkedIn, ...)"),
    _:      str           = Depends(verify_token),
):
    """
    Конверсия откликов по источникам: applied → interview → offer.

    conv_pct = offer / applied * 100.
    Помогает понять, какой источник вакансий эффективнее.
    """
    from automation.analytics import conversion_by_source, AnalyticsError  # noqa: PLC0415
    try:
        client = _get_ch_client()
        data = conversion_by_source(client, source=source)
        return [ConversionItem(**row) for row in data]
    except HTTPException:
        raise
    except AnalyticsError as exc:
        logger.error("/analytics/conversion: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/skill-trends", response_model=list[SkillTrendItem])
async def get_skill_trends(
    months: int = Query(3, ge=1, le=12, description="За сколько месяцев"),
    _:      str = Depends(verify_token),
):
    """
    Тренды skill gaps за N месяцев.

    trend: "up" — навык встречается чаще (растущий спрос),
           "down" — реже, "stable" — без изменений.
    Помогает понять, какие навыки изучать приоритетно.
    """
    from automation.analytics import skill_gap_trends, AnalyticsError  # noqa: PLC0415
    try:
        client = _get_ch_client()
        data = skill_gap_trends(client, months=months)
        return [SkillTrendItem(**row) for row in data]
    except HTTPException:
        raise
    except AnalyticsError as exc:
        logger.error("/analytics/skill-trends: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/salary-by-stack", response_model=list[SalaryStackItem])
async def get_salary_by_stack(
    _: str = Depends(verify_token),
):
    """
    Средняя зарплата по технологическому стеку.

    Только вакансии с указанной зарплатой (salary_from > 0).
    Минимум 2 вакансии для включения в выборку.
    """
    from automation.analytics import salary_by_stack, AnalyticsError  # noqa: PLC0415
    try:
        client = _get_ch_client()
        data = salary_by_stack(client)
        return [SalaryStackItem(**row) for row in data]
    except HTTPException:
        raise
    except AnalyticsError as exc:
        logger.error("/analytics/salary-by-stack: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
