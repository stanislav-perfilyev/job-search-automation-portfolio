"""
app/routers/vacancies.py

GET  /vacancies          — список с фильтрами
POST /vacancies          — добавить (upsert по url)
PATCH /vacancies/{id}    — обновить статус/заметки
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.models.vacancy import Vacancy
from app.schemas.vacancy import VacancyCreate, VacancyOut, VacancyPatch

router = APIRouter(prefix="/vacancies", tags=["vacancies"])


@router.get("", response_model=list[VacancyOut])
async def list_vacancies(
    status_filter: str | None = Query(None, alias="status"),
    source:        str | None = Query(None),
    date_from:     date | None = Query(None),
    date_to:       date | None = Query(None),
    limit:         int         = Query(100, ge=1, le=500),
    offset:        int         = Query(0, ge=0),
    db:            AsyncSession = Depends(get_db),
    _:             str          = Depends(verify_token),
):
    q = (
        select(Vacancy)
        .order_by(Vacancy.date.desc(), Vacancy.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        q = q.where(Vacancy.status == status_filter)
    if source:
        q = q.where(Vacancy.source == source)
    if date_from:
        q = q.where(Vacancy.date >= date_from)
    if date_to:
        q = q.where(Vacancy.date <= date_to)

    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=VacancyOut, status_code=status.HTTP_201_CREATED)
async def create_vacancy(
    body: VacancyCreate,
    db:   AsyncSession = Depends(get_db),
    _:    str          = Depends(verify_token),
):
    """Добавляет вакансию. При конфликте url — обновляет статус и notes."""
    stmt = (
        pg_insert(Vacancy)
        .values(**body.model_dump())
        .on_conflict_do_update(
            index_elements=["url"],
            set_={
                "status":     body.status,
                "notes":      body.notes,
                "skill_gaps": body.skill_gaps,
            },
        )
        .returning(Vacancy)
    )
    result = await db.execute(stmt)
    await db.commit()
    row = result.fetchone()
    # returning даёт Row, а не ORM-объект — делаем отдельный select
    vac = await db.get(Vacancy, row[0].id)
    return vac


@router.patch("/{vacancy_id}", response_model=VacancyOut)
async def patch_vacancy(
    vacancy_id: int,
    body:       VacancyPatch,
    db:         AsyncSession = Depends(get_db),
    _:          str          = Depends(verify_token),
):
    vac = await db.get(Vacancy, vacancy_id)
    if vac is None:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Нечего обновлять")

    for field, value in updates.items():
        setattr(vac, field, value)
    await db.commit()
    await db.refresh(vac)
    return vac


@router.delete("/{vacancy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vacancy(
    vacancy_id: int,
    db:         AsyncSession = Depends(get_db),
    _:          str          = Depends(verify_token),
):
    vac = await db.get(Vacancy, vacancy_id)
    if vac is None:
        raise HTTPException(status_code=404, detail="Вакансия не найдена")
    await db.delete(vac)
    await db.commit()
