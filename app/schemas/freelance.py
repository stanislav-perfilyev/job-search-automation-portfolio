"""
app/schemas/freelance.py — Pydantic v2 схемы для фриланс-проектов.
"""
from datetime import date as _date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class FreelanceCreate(BaseModel):
    project_title:  str              = Field(..., min_length=1, max_length=500)
    platform:       str              = Field(..., min_length=1, max_length=50)
    date:           _date            = Field(default_factory=_date.today)
    client:         Optional[str]    = None
    url:            Optional[str]    = None
    budget:         Optional[Decimal] = Field(None, ge=0)
    our_rate:       Optional[Decimal] = Field(None, ge=0)
    connects_spent: int              = Field(0, ge=0)
    template_used:  Optional[str]    = None
    comment:        Optional[str]    = None
    status:         Literal[
        "sent", "viewed", "interview", "contract", "rejected", "closed"
    ] = "sent"


class FreelancePatch(BaseModel):
    status:  Optional[Literal[
        "sent", "viewed", "interview", "contract", "rejected", "closed"
    ]] = None
    comment: Optional[str] = None


class FreelanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:             int
    date:           _date
    platform:       str
    project_title:  str
    client:         Optional[str]
    url:            Optional[str]
    budget:         Optional[Decimal]
    our_rate:       Optional[Decimal]
    connects_spent: int
    template_used:  Optional[str]
    comment:        Optional[str]
    status:         str
    created_at:     datetime
