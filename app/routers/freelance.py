"""
app/routers/freelance.py

GET  /freelance     — список проектов
POST /freelance     — добавить (upsert по url)
PATCH /freelance/{id} — обновить статус
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.models.freelance import FreelanceProject
from app.schemas.freelance import FreelanceCreate, FreelanceOut, FreelancePatch

router = APIRouter(prefix="/freelance", tags=["freelance"])


@router.get("", response_model=list[FreelanceOut])
async def list_freelance(
    status_filter: str | None = Query(None, alias="status"),
    platform:      str | None = Query(None),
    limit:         int         = Query(50, ge=1, le=200),
    offset:        int         = Query(0, ge=0),
    db:            AsyncSession = Depends(get_db),
    _:             str          = Depends(verify_token),
):
    q = (
        select(FreelanceProject)
        .order_by(FreelanceProject.date.desc(), FreelanceProject.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        q = q.where(FreelanceProject.status == status_filter)
    if platform:
        q = q.where(FreelanceProject.platform == platform)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=FreelanceOut, status_code=status.HTTP_201_CREATED)
async def create_freelance(
    body: FreelanceCreate,
    db:   AsyncSession = Depends(get_db),
    _:    str          = Depends(verify_token),
):
    data = body.model_dump()

    # Если url = None — просто INSERT (NULL не конфликтует)
    if data.get("url") is None:
        proj = FreelanceProject(**data)
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        return proj

    stmt = (
        pg_insert(FreelanceProject)
        .values(**data)
        .on_conflict_do_update(
            constraint="freelance_url_unique",
            set_={"status": body.status, "comment": body.comment},
        )
        .returning(FreelanceProject.id)
    )
    result = await db.execute(stmt)
    await db.commit()
    proj_id = result.scalar_one()
    return await db.get(FreelanceProject, proj_id)


@router.patch("/{project_id}", response_model=FreelanceOut)
async def patch_freelance(
    project_id: int,
    body:       FreelancePatch,
    db:         AsyncSession = Depends(get_db),
    _:          str          = Depends(verify_token),
):
    proj = await db.get(FreelanceProject, project_id)
    if proj is None:
        raise HTTPException(status_code=404, detail="Проект не найден")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Нечего обновлять")

    for field, value in updates.items():
        setattr(proj, field, value)
    await db.commit()
    await db.refresh(proj)
    return proj
