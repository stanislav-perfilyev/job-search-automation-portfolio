"""
app/routers/kpi.py

GET  /kpi              — агрегированные KPI данные для дашборда
POST /kpi/event        — логировать событие
GET  /kpi/event_types  — список типов событий
"""
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.cache import cache
from app.database import get_db
from app.models.kpi_event import KpiEvent
from app.models.vacancy import Vacancy
from app.models.freelance import FreelanceProject

router = APIRouter(prefix="/kpi", tags=["kpi"])

_KPI_TTL = 120   # 2 минуты кэш


# ── Схемы ─────────────────────────────────────────────────────────────────────

class KpiEventIn(BaseModel):
    event_type: str
    value: float = 1.0
    meta: dict[str, Any] | None = None


class KpiEventOut(BaseModel):
    id: int
    event_type: str
    value: float
    meta: dict[str, Any] | None
    created_at: datetime


# ── Эндпоинты ─────────────────────────────────────────────────────────────────

@router.get("")
async def get_kpi(
    days: int          = Query(30, ge=7, le=365, description="Период в днях"),
    db:   AsyncSession = Depends(get_db),
    _:    str          = Depends(verify_token),
) -> dict:
    """Агрегированные KPI данные для Chart.js дашборда."""
    cache_key = f"kpi:{days}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    since = date.today() - timedelta(days=days)

    # ── Вакансии по неделям ──────────────────────────────────────────────────
    vac_rows = await db.execute(
        text("""
            SELECT
                DATE_TRUNC('week', date)::date    AS week,
                COUNT(*)                          AS total,
                COUNT(*) FILTER (WHERE status = 'applied')   AS applied,
                COUNT(*) FILTER (WHERE status = 'interview') AS interview,
                COUNT(*) FILTER (WHERE status = 'offer')     AS offer,
                COUNT(*) FILTER (WHERE status = 'rejected')  AS rejected
            FROM vacancies
            WHERE date >= :since
            GROUP BY week
            ORDER BY week
        """),
        {"since": since},
    )
    weekly_vac = [
        {
            "week":      str(r.week),
            "label":     r.week.strftime("%d.%m"),
            "total":     r.total,
            "applied":   r.applied,
            "interview": r.interview,
            "offer":     r.offer,
            "rejected":  r.rejected,
        }
        for r in vac_rows
    ]

    # ── Фриланс по неделям ───────────────────────────────────────────────────
    fl_rows = await db.execute(
        text("""
            SELECT
                DATE_TRUNC('week', date)::date    AS week,
                COUNT(*)                          AS total,
                COUNT(*) FILTER (WHERE status = 'contract') AS contracts
            FROM freelance_projects
            WHERE date >= :since
            GROUP BY week
            ORDER BY week
        """),
        {"since": since},
    )
    weekly_fl = [
        {
            "week":      str(r.week),
            "label":     r.week.strftime("%d.%m"),
            "total":     r.total,
            "contracts": r.contracts,
        }
        for r in fl_rows
    ]

    # ── KPI события по типам и неделям ───────────────────────────────────────
    ev_rows = await db.execute(
        text("""
            SELECT
                DATE_TRUNC('week', created_at)::date    AS week,
                event_type,
                SUM(value)::float                       AS total_value,
                COUNT(*)                                AS count
            FROM kpi_events
            WHERE created_at >= :since
            GROUP BY week, event_type
            ORDER BY week
        """),
        {"since": since},
    )
    weekly_events = [
        {
            "week":        str(r.week),
            "label":       r.week.strftime("%d.%m"),
            "event_type":  r.event_type,
            "total_value": float(r.total_value or 0),
            "count":       int(r.count),
        }
        for r in ev_rows
    ]

    # ── Воронка (всего за период) ─────────────────────────────────────────────
    funnel_row = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status IN ('applied','new')) AS applied,
                COUNT(*) FILTER (WHERE status = 'interview')        AS interview,
                COUNT(*) FILTER (WHERE status = 'offer')            AS offer,
                COUNT(*) FILTER (WHERE status = 'rejected')         AS rejected
            FROM vacancies
            WHERE date >= :since
        """),
        {"since": since},
    )
    fr = funnel_row.one()

    # ── Сводка ───────────────────────────────────────────────────────────────
    total_vac = sum(w["total"] for w in weekly_vac)
    total_fl  = sum(w["total"] for w in weekly_fl)
    code_lines = sum(
        e["total_value"] for e in weekly_events if e["event_type"] == "code_lines"
    )
    sessions = sum(
        e["count"] for e in weekly_events
        if e["event_type"] in ("job_session", "freelance_session")
    )
    portfolio = sum(
        e["count"] for e in weekly_events if e["event_type"] == "portfolio_project"
    )

    result = {
        "period_days":     days,
        "since":           since.isoformat(),
        "generated_at":    datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": {
            "total_vacancies":    total_vac,
            "total_freelance":    total_fl,
            "code_lines":         int(code_lines),
            "sessions":           sessions,
            "portfolio_projects": portfolio,
            "interview":          fr.interview,
            "offer":              fr.offer,
            "rejected":           fr.rejected,
        },
        "funnel":          {
            "applied":   fr.applied,
            "interview": fr.interview,
            "offer":     fr.offer,
            "rejected":  fr.rejected,
        },
        "weekly_vacancies": weekly_vac,
        "weekly_freelance": weekly_fl,
        "weekly_events":    weekly_events,
    }

    await cache.set(cache_key, result, ttl=_KPI_TTL)
    return result


@router.post("/event", response_model=KpiEventOut, status_code=201)
async def log_kpi_event(
    payload: KpiEventIn,
    db:      AsyncSession = Depends(get_db),
    _:       str          = Depends(verify_token),
):
    """Логировать KPI-событие (из скриптов или вручную)."""
    ev = KpiEvent(
        event_type=payload.event_type,
        value=payload.value,
        meta=payload.meta,
    )
    db.add(ev)
    await db.commit()
    await db.refresh(ev)
    # Сброс кэша KPI
    await cache.delete_pattern("kpi:*")
    return ev


@router.get("/event_types")
async def list_event_types(
    db: AsyncSession = Depends(get_db),
    _:  str          = Depends(verify_token),
) -> list[str]:
    """Возвращает уникальные типы событий в kpi_events."""
    rows = await db.execute(
        select(KpiEvent.event_type).distinct().order_by(KpiEvent.event_type)
    )
    return [r[0] for r in rows]
