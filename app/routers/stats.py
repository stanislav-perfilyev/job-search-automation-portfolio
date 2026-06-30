"""
app/routers/stats.py

GET /stats        — сводная статистика (кэшируется в Redis 5 минут)
GET /stats/chart  — данные для Chart.js
DELETE /stats/cache — сброс кэша (принудительное обновление)
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.cache import cache
from app.database import get_db
from app.models.vacancy import Vacancy
from app.models.freelance import FreelanceProject
from app.schemas.stats import ChartDataset, ChartOut, FreelanceStats, StatsOut, VacancyStats

router = APIRouter(prefix="/stats", tags=["stats"])

_STATS_TTL = 300   # 5 минут


@router.get("", response_model=StatsOut)
async def get_stats(
    days: int          = Query(7, ge=1, le=365, description="Период в днях"),
    db:   AsyncSession = Depends(get_db),
    _:    str          = Depends(verify_token),
):
    cache_key = f"stats:{days}"

    # Попытка взять из кэша
    cached = await cache.get(cache_key)
    if cached:
        return StatsOut(**cached)

    since = date.today() - timedelta(days=days)

    vac_row = await db.execute(
        select(
            func.count().label("total"),
            func.count(case((Vacancy.status == "applied",   1))).label("applied"),
            func.count(case((Vacancy.status == "interview", 1))).label("interview"),
            func.count(case((Vacancy.status == "offer",     1))).label("offer"),
            func.count(case((Vacancy.status == "rejected",  1))).label("rejected"),
            func.count(case((Vacancy.status == "new",       1))).label("new"),
        ).where(Vacancy.date >= since)
    )
    vr = vac_row.one()

    fl_row = await db.execute(
        select(
            func.count().label("total"),
            func.coalesce(func.sum(FreelanceProject.connects_spent), 0).label("connects_used"),
            func.count(case((FreelanceProject.status == "contract",  1))).label("contracts"),
            func.count(case((FreelanceProject.status == "interview", 1))).label("interviews"),
        ).where(FreelanceProject.date >= since)
    )
    fr = fl_row.one()

    result = StatsOut(
        period_days=days,
        vacancies=VacancyStats(
            total=vr.total, applied=vr.applied, interview=vr.interview,
            offer=vr.offer, rejected=vr.rejected, new=vr.new,
        ),
        freelance=FreelanceStats(
            total=fr.total, connects_used=fr.connects_used,
            contracts=fr.contracts, interviews=fr.interviews,
        ),
    )

    # Сохраняем в кэш
    await cache.set(cache_key, result.model_dump(), ttl=_STATS_TTL)
    return result


@router.delete("/cache", status_code=204)
async def clear_stats_cache(
    _: str = Depends(verify_token),
):
    """Сбросить кэш статистики (Redis). Полезно после импорта данных."""
    await cache.delete_pattern("stats:*")


@router.get("/chart", response_model=ChartOut)
async def get_chart(
    days: int          = Query(30, ge=7, le=180),
    db:   AsyncSession = Depends(get_db),
    _:    str          = Depends(verify_token),
):
    since = date.today() - timedelta(days=days)

    rows = await db.execute(
        select(Vacancy.date, func.count().label("cnt"))
        .where(Vacancy.date >= since)
        .group_by(Vacancy.date)
        .order_by(Vacancy.date)
    )
    by_date = {r.date: r.cnt for r in rows}

    labels: list[str] = []
    data:   list[int] = []
    for i in range(days):
        d = since + timedelta(days=i + 1)
        labels.append(d.strftime("%d.%m"))
        data.append(by_date.get(d, 0))

    return ChartOut(
        labels=labels,
        datasets=[
            ChartDataset(label="Вакансии", data=data,
                         backgroundColor="#4fc3f7", borderColor="#0288d1"),
        ],
    )
