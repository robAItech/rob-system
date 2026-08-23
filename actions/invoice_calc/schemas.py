"""Pydantic V2 sheme za modul invoice_calc — izračun faktur z DDV in popusti.

Sheme so stroge: napačni tipi (bool namesto števila, float namesto int,
neprepoznavne vrednosti, dodatna polja) se zavrnejo že ob validaciji.
Vse denarne vrednosti so Decimal (brez artefaktov plavajoče vejice).
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, List

from pydantic import BaseModel, ConfigDict, Field, field_validator


def to_decimal(value: Any) -> Decimal:
    """Pretvori int/float/str/Decimal v Decimal brez plavajoče-vejice artefaktov."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("vrednost ne sme biti bool")
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except Exception as exc:  # noqa: BLE001 — zavrnemo neveljaven niz
            raise ValueError(f"neveljavna decimalna vrednost: {value!r}") from exc
    raise ValueError(f"neveljavna decimalna vrednost: {value!r}")


def round_money(value: Decimal, places: int = 2) -> Decimal:
    """Zaokroži denarno vrednost na `places` decimalk (polovično navzgor)."""
    return Decimal(value).quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def _require_decimal(
    value: Any,
    field: str,
    minimum: Decimal | None = None,
    maximum: Decimal | None = None,
    exclusive_minimum: bool = False,
) -> Decimal:
    dec = to_decimal(value)
    if minimum is not None:
        if (exclusive_minimum and dec <= minimum) or (not exclusive_minimum and dec < minimum):
            op = ">" if exclusive_minimum else ">="
            raise ValueError(f"{field} mora biti {op} {minimum}")
    if maximum is not None and dec > maximum:
        raise ValueError(f"{field} mora biti <= {maximum}")
    return dec


class InvoiceItem(BaseModel):
    """Posamezna postavka na fakturi."""

    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: int
    unit_price: Decimal
    discount_percent: Decimal = Field(default=Decimal("0"))

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("opis postavke ne sme biti prazen")
        return value.strip()

    @field_validator("quantity", mode="before")
    @classmethod
    def _validate_quantity(cls, value: Any) -> int:
        # mode="before": Pydantic V2 v lax načinu pretvori bool → int (True → 1),
        # zato moramo surovi vhod pregledati PRED tipsko koercijo, sicer bi
        # `quantity=True` tiho postalo 1 in ušlo validaciji.
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("količina mora biti pozitivno celo število")
        return value

    @field_validator("unit_price", mode="before")
    @classmethod
    def _validate_unit_price(cls, value: Any) -> Decimal:
        return _require_decimal(
            value, "unit_price", minimum=Decimal("0"), exclusive_minimum=True
        )

    @field_validator("discount_percent", mode="before")
    @classmethod
    def _validate_discount_percent(cls, value: Any) -> Decimal:
        return _require_decimal(
            value, "discount_percent", minimum=Decimal("0"), maximum=Decimal("100")
        )


class InvoiceRequest(BaseModel):
    """Celotna faktura: postavke, stopnja DDV in popust."""

    model_config = ConfigDict(extra="forbid")

    items: List[InvoiceItem] = Field(..., min_length=1)
    vat_rate: Decimal = Field(default=Decimal("0"))
    discount_percent: Decimal = Field(default=Decimal("0"))
    currency: str = Field(default="EUR", min_length=3, max_length=3)

    @field_validator("items")
    @classmethod
    def _validate_items(cls, value: List[InvoiceItem]) -> List[InvoiceItem]:
        if not value:
            raise ValueError("faktura mora vsebovati vsaj eno postavko")
        return value

    @field_validator("vat_rate", mode="before")
    @classmethod
    def _validate_vat_rate(cls, value: Any) -> Decimal:
        return _require_decimal(value, "vat_rate", minimum=Decimal("0"))

    @field_validator("discount_percent", mode="before")
    @classmethod
    def _validate_discount_percent(cls, value: Any) -> Decimal:
        return _require_decimal(
            value, "discount_percent", minimum=Decimal("0"), maximum=Decimal("100")
        )

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: Any) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) != 3:
            raise ValueError("valuta mora biti 3-mestna oznaka ISO 4217")
        return value.strip().upper()


class InvoiceResult(BaseModel):
    """Rezultat izračuna fakture (vse vrednosti zaokrožene na 2 decimalki)."""

    model_config = ConfigDict(extra="forbid")

    currency: str
    item_count: int
    subtotal: Decimal
    discount_amount: Decimal
    taxable_amount: Decimal
    vat_amount: Decimal
    total: Decimal

    @property
    def net(self) -> Decimal:
        """Sinonim za obdavčljiv znesek (po popustih, pred DDV)."""
        return self.taxable_amount

    @property
    def vat(self) -> Decimal:
        """Sinonim za znesek DDV."""
        return self.vat_amount

    @property
    def discount(self) -> Decimal:
        """Sinonim za skupni znesek popusta."""
        return self.discount_amount


# Priročna imenska sopomenka za združljivost z različnimi poimenovanji.
InvoiceLine = InvoiceItem
Invoice = InvoiceRequest

__all__ = [
    "Invoice",
    "InvoiceItem",
    "InvoiceLine",
    "InvoiceRequest",
    "InvoiceResult",
    "round_money",
    "to_decimal",
]