"""Pydantic V2 sheme za finance_calc API."""

from __future__ import annotations

import math
from typing import List

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "VatPriceRequest",
    "DiscountPriceRequest",
    "FormatEurRequest",
    "CagrRequest",
    "PriceResponse",
    "EurResponse",
    "CagrResponse",
]


def _finite(value: float) -> float:
    """Stroga validacija: vrednost mora biti končno število."""
    if not math.isfinite(value):
        raise ValueError("vrednost mora biti končno število")
    return value


class VatPriceRequest(BaseModel):
    """Zahtevek za izračun cene z DDV."""

    price: float = Field(..., description="Neto cena")
    rate: float = Field(0.22, description="DDV stopnja (npr. 0.22 za 22 %)")

    @field_validator("price", "rate")
    @classmethod
    def check_finite(cls, v: float) -> float:
        return _finite(v)


class DiscountPriceRequest(BaseModel):
    """Zahtevek za izračun cene s popustom."""

    price: float = Field(..., description="Cena pred popustom")
    percent: float = Field(
        ..., ge=0, le=100, description="Popust v odstotkih (0–100)"
    )

    @field_validator("price", "percent")
    @classmethod
    def check_finite(cls, v: float) -> float:
        return _finite(v)


class FormatEurRequest(BaseModel):
    """Zahtevek za oblikovanje zneska v EUR."""

    value: float = Field(..., description="Znesek v EUR")

    @field_validator("value")
    @classmethod
    def check_finite(cls, v: float) -> float:
        return _finite(v)


class CagrRequest(BaseModel):
    """Zahtevek za izračun CAGR."""

    values: List[float] = Field(..., description="Letne vrednosti")

    @field_validator("values")
    @classmethod
    def check_finite(cls, v: List[float]) -> List[float]:
        for item in v:
            _finite(item)
        return v


class PriceResponse(BaseModel):
    """Odgovor z izračunano ceno."""

    price: float


class EurResponse(BaseModel):
    """Odgovor z oblikovanim EUR nizom."""

    value: str


class CagrResponse(BaseModel):
    """Odgovor z izračunano rastjo."""

    cagr: float