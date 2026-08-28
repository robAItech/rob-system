"""schemas.py — Pydantic V2 sheme za upravljanje izdelkov in zalog.

Strogi validatorji zagotavljajo robne pogoje:
  - SKU je obvezen, nestandarden (presledki) se očistijo,
  - cena in količine so strogo pozitivne (ali nenegativne, kjer je to smiselno),
  - status izdelka in tip premika sta omejena na dovoljene vrednosti,
  - reorder_level ne sme biti negativen.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_QUANTITY = 1_000_000


def utc_now() -> datetime:
    """Deterministična časovna oznaka v UTC (brez microseconds za teste)."""
    return datetime.now(timezone.utc).replace(microsecond=0)


class ProductStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISCONTINUED = "discontinued"


class MovementType(str, Enum):
    IN = "in"
    OUT = "out"
    ADJUST = "adjust"


class ProductBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., min_length=1, max_length=64, description="Unikatna SKU oznaka")
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., gt=0, description="Cena mora biti strogo pozitivna")
    status: ProductStatus = ProductStatus.ACTIVE
    reorder_level: int = Field(0, ge=0, description="Prag za opozorilo o nizki zalogi")

    @field_validator("sku", mode="before")
    @classmethod
    def _clean_sku(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("SKU ne sme biti prazen")
            return cleaned
        return v

    @field_validator("name", "category", mode="before")
    @classmethod
    def _clean_text(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Polje ne sme biti prazno")
            return cleaned
        return v


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: Optional[str] = Field(None, min_length=1, max_length=64)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    price: Optional[float] = Field(None, gt=0)
    status: Optional[ProductStatus] = None
    reorder_level: Optional[int] = Field(None, ge=0)

    @field_validator("sku", mode="before")
    @classmethod
    def _clean_sku(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("SKU ne sme biti prazen")
            return cleaned
        return v

    @field_validator("name", "category", mode="before")
    @classmethod
    def _clean_text(cls, v: object) -> object:
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Polje ne sme biti prazno")
            return cleaned
        return v


class Product(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class StockAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: MovementType
    quantity: int = Field(..., gt=0, description="Količina mora biti pozitivna")
    reason: str = Field("", max_length=200)


class StockLevel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    quantity: int = Field(..., ge=0, le=MAX_QUANTITY)
    updated_at: datetime = Field(default_factory=utc_now)


class StockMovement(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    type: MovementType
    quantity: int = Field(..., gt=0)
    reason: str = Field("", max_length=200)
    created_at: datetime = Field(default_factory=utc_now)
