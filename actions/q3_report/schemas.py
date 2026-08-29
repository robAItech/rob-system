"""Pydantic V2 sheme za Q3 poročilo."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class Q3Metric(BaseModel):
    """Posamezen KPI, vključen v Q3 poročilo."""

    name: str = Field(min_length=1)
    value: float = Field(ge=0)
    unit: str = Field(default="")

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name ne sme biti prazen")
        return v


class Q3ReportData(BaseModel):
    """Podatki, potrebni za izdelavo Markdown poročila o rezultatih Q3."""

    quarter: str = Field(default="Q3 2025")
    revenue: float = Field(ge=0)
    expenses: float = Field(ge=0)
    profit: Optional[float] = Field(default=None, ge=0)
    customers: int = Field(default=0, ge=0)
    metrics: list[Q3Metric] = Field(default_factory=list)

    @field_validator("quarter")
    @classmethod
    def quarter_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("quarter ne sme biti prazen")
        return v

    @model_validator(mode="after")
    def _compute_profit(self) -> "Q3ReportData":
        if self.profit is None:
            self.profit = self.revenue - self.expenses
        return self