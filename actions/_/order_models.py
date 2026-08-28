"""order_models — Pydantic V2 sheme naročil.

- ``Item``: sku, name, price >= 0, quantity > 0.
- ``Order``: id, customer, items (non-empty), total >= 0.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Item(BaseModel):
    """Posamezna postavka naročila."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    sku: str = Field(..., min_length=1, description="Identifikator izdelka")
    name: str = Field(..., min_length=1, description="Ime izdelka")
    price: float = Field(..., ge=0, description="Cena brez DDV")
    quantity: int = Field(..., gt=0, description="Količina (mora biti > 0)")

    @field_validator("sku", "name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("Polje ne sme biti prazno")
        return value

    @field_validator("price")
    @classmethod
    def _finite_price(cls, value: float) -> float:
        if value is None:
            raise ValueError("Cena je obvezna")
        import math

        if not math.isfinite(value):
            raise ValueError("Cena mora biti končno število")
        return value


class Order(BaseModel):
    """Naročilo z vsaj eno postavko in nenegativnim zneskom."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    id: str = Field(..., min_length=1, description="Identifikator naročila")
    customer: str = Field(..., min_length=1, description="Ime stranke")
    items: List[Item] = Field(..., description="Postavke naročila")
    total: float = Field(..., ge=0, description="Skupni znesek (z DDV)")

    @field_validator("id", "customer")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("Polje ne sme biti prazno")
        return value

    @model_validator(mode="after")
    def _items_not_empty(self) -> "Order":
        if not self.items:
            raise ValueError("Naročilo mora vsebovati vsaj eno postavko")
        return self

    @field_validator("total")
    @classmethod
    def _finite_total(cls, value: float) -> float:
        if value is None:
            raise ValueError("Znesek je obvezen")
        import math

        if not math.isfinite(value):
            raise ValueError("Znesek mora biti končno število")
        return value