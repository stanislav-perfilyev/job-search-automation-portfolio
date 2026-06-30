"""
app/models/freelance.py — SQLAlchemy ORM-модель таблицы freelance_projects.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

VALID_STATUSES = ("sent", "viewed", "interview", "contract", "rejected", "closed")


class FreelanceProject(Base):
    __tablename__ = "freelance_projects"
    __table_args__ = (
        CheckConstraint(
            "status IN ('sent','viewed','interview','contract','rejected','closed')",
            name="freelance_status_check",
        ),
    )

    id:             Mapped[int]            = mapped_column(Integer, primary_key=True)
    date:           Mapped[date]           = mapped_column(Date, nullable=False)
    platform:       Mapped[str]            = mapped_column(Text, nullable=False)
    project_title:  Mapped[str]            = mapped_column(Text, nullable=False)
    client:         Mapped[str | None]     = mapped_column(Text, nullable=True)
    url:            Mapped[str | None]     = mapped_column(Text, nullable=True, unique=True)
    budget:         Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    our_rate:       Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    connects_spent: Mapped[int]            = mapped_column(Integer, default=0)
    template_used:  Mapped[str | None]     = mapped_column(Text, nullable=True)
    comment:        Mapped[str | None]     = mapped_column(Text, nullable=True)
    status:         Mapped[str]            = mapped_column(Text, default="sent")
    created_at:     Mapped[datetime]       = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
