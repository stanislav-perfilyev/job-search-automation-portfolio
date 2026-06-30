"""
app/models/vacancy.py — SQLAlchemy ORM-модель таблицы vacancies.
Схема соответствует init_db.py (не меняет структуру, только отражает её).
"""
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

VALID_STATUSES = ("new", "applied", "interview", "offer", "rejected", "ignored")


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (
        CheckConstraint(
            "status IN ('new','applied','interview','offer','rejected','ignored')",
            name="vacancies_status_check",
        ),
    )

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True)
    date:         Mapped[date]          = mapped_column(Date, nullable=False)
    title:        Mapped[str]           = mapped_column(Text, nullable=False)
    company:      Mapped[str]           = mapped_column(Text, nullable=False)
    url:          Mapped[str]           = mapped_column(Text, nullable=False, unique=True)
    salary_min:   Mapped[int | None]    = mapped_column(Integer, nullable=True)
    salary_max:   Mapped[int | None]    = mapped_column(Integer, nullable=True)
    currency:     Mapped[str]           = mapped_column(Text, default="KZT")
    source:       Mapped[str]           = mapped_column(Text, nullable=False)
    status:       Mapped[str]           = mapped_column(Text, default="applied")
    template_used:Mapped[str | None]    = mapped_column(Text, nullable=True)
    skill_gaps:   Mapped[str | None]    = mapped_column(Text, nullable=True)
    notes:        Mapped[str | None]    = mapped_column(Text, nullable=True)
    created_at:   Mapped[datetime]      = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
