"""
app/schemas/stats.py — Pydantic v2 схемы для статистики.
"""
from pydantic import BaseModel


class VacancyStats(BaseModel):
    total:      int
    applied:    int
    interview:  int
    offer:      int
    rejected:   int
    new:        int


class FreelanceStats(BaseModel):
    total:         int
    connects_used: int
    contracts:     int
    interviews:    int


class StatsOut(BaseModel):
    period_days: int
    vacancies:   VacancyStats
    freelance:   FreelanceStats


class ChartDataset(BaseModel):
    label: str
    data:  list[int]
    backgroundColor: str = "#4fc3f7"
    borderColor:     str = "#0288d1"
    tension:         float = 0.3


class ChartOut(BaseModel):
    labels:   list[str]
    datasets: list[ChartDataset]
