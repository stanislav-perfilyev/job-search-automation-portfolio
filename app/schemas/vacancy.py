"""
app/schemas/vacancy.py — Pydantic v2 схемы для вакансий.
"""
from datetime import date as _date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VacancyCreate(BaseModel):
    title:         str           = Field(..., min_length=1, max_length=500)
    company:       str           = Field(..., min_length=1, max_length=300)
    url:           str           = Field(..., min_length=1)
    source:        str           = Field(..., min_length=1, max_length=100)
    date:          _date         = Field(default_factory=_date.today)
    salary_min:    Optional[int] = Field(None, ge=0)
    salary_max:    Optional[int] = Field(None, ge=0)
    currency:      str           = Field("KZT", max_length=20)
    status:        Literal[
        "new", "applied", "interview", "offer", "rejected", "ignored"
    ] = "applied"
    template_used: Optional[str] = None
    skill_gaps:    Optional[str] = None
    notes:         Optional[str] = None

    @field_validator("salary_max")
    @classmethod
    def max_gte_min(cls, v, info):
        mn = info.data.get("salary_min")
        if v is not None and mn is not None and v < mn:
            raise ValueError("salary_max должен быть >= salary_min")
        return v


class VacancyPatch(BaseModel):
    status:     Optional[Literal[
        "new", "applied", "interview", "offer", "rejected", "ignored"
    ]] = None
    notes:      Optional[str] = None
    skill_gaps: Optional[str] = None


class VacancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:            int
    date:          _date
    title:         str
    company:       str
    url:           str
    source:        str
    salary_min:    Optional[int]
    salary_max:    Optional[int]
    currency:      str
    status:        str
    template_used: Optional[str]
    skill_gaps:    Optional[str]
    notes:         Optional[str]
    created_at:    datetime
