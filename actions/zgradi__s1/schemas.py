"""schemas.py — Pydantic V2 sheme sistema za upravljanje naročil.

Skupna podatkovna shema: stranka, naslov, postavke, plačilo in naročilo,
s strogimi validatorji za robne pogoje (negativne cene, prazna naročila,
nedovoljeni statusi, količine itd.).

Vse sheme uporabljajo Pydantic V2 (field_validator/model_validator) in
vrnejo ValueError → Pydantic jih pretvori v validation errors.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Skupne konstante in pomožne funkcije
# ---------------------------------------------------------------------------

def utc_now() -> datetime:
    """Trenutni čas v UTC (naivni, determinističen za primerjave)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def money(value: float | int | str | Decimal) -> Decimal:
    """Pretvori vrednost v Decimal, zaokrožen na 2 decimalki (polovično navzgor)."""
    if isinstance(value, bool):
        raise TypeError("bool ni veljavna denarna vrednost")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class OrderStatus(str, Enum):
    """Dovoljeni statusi življenjskega cikla naročila."""

    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentMethod(str, Enum):
    """Podprte plačilne metode."""

    CARD = "card"
    PAYPAL = "paypal"
    BANK_TRANSFER = "bank_transfer"
    CASH_ON_DELIVERY = "cash_on_delivery"


# ---------------------------------------------------------------------------
# Podatkovne sheme
# ---------------------------------------------------------------------------

class Address(BaseModel):
    """Naslov za dostavo / plačilo."""

    street: str = Field(..., min_length=1, max_length=200)
    city: str = Field(..., min_length=1, max_length=100)
    postal_code: str = Field(..., min_length=1, max_length=20)
    country: str = Field(..., min_length=1, max_length=100)

    @field_validator("street", "city", "postal_code", "country")
    @classmethod
    def _strip_and_check(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("polje ne sme biti prazno")
        return value


class Customer(BaseModel):
    """Podatki o stranki, ki naroča."""

    name: str = Field(..., min_length=1, max_length=150)
    email: str = Field(..., min_length=3, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=30)
    address: Optional[Address] = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("ime ne sme biti prazno")
        return value

    @field_validator("email")
    @classmethod
    def _email_has_at(cls, value: str) -> str:
        value = value.strip()
        if "@" not in value:
            raise ValueError("email mora vsebovati @")
        return value


class OrderItem(BaseModel):
    """Enaka postavka v naročilu."""

    product_id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(..., ge=1, le=1000)
    unit_price: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)

    @field_validator("product_id", "name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("polje ne sme biti prazno")
        return value

    @field_validator("unit_price", mode="before")
    @classmethod
    def _round_price(cls, value: Any) -> Decimal:
        # mode="before": zaokrožimo PRED preverjanjem decimal_places/gt,
        # da npr. 1.005 -> 1.01, 9.999 -> 10.00 (ne pa padec validacije).
        return money(value)


class Payment(BaseModel):
    """Podatki o plačilu naročila."""

    method: PaymentMethod = PaymentMethod.CARD
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)

    @field_validator("amount", mode="before")
    @classmethod
    def _round_amount(cls, value: Any) -> Decimal:
        return money(value)


class OrderCreate(BaseModel):
    """Vhodna shema za ustvarjanje naročila.

    ``payment`` je opcijski: če ni podan (ali je znesek 0), domenska logika
    sama izračuna predviden znesek iz postavk (total). Znesek 0 se tu
    normalizira v ``None``, da validacija ``gt=0`` ne blokira dokumentiranega
    vodenja; negativni zneski ostanejo strogo zavrnjeni (gt=0).
    """

    customer: Customer
    items: List[OrderItem] = Field(..., min_length=1)
    payment: Optional[Payment] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _normalize_zero_payment(cls, data: Any) -> Any:
        """Znesek plačila 0 -> brez plačila (domenska logika izračuna total)."""
        if isinstance(data, dict):
            payment = data.get("payment")
            if isinstance(payment, dict):
                amount = payment.get("amount")
                if amount is not None:
                    try:
                        is_zero = Decimal(str(amount)) == 0
                    except (InvalidOperation, ValueError, TypeError):
                        is_zero = False
                    if is_zero:
                        data = {**data, "payment": None}
        return data

    @model_validator(mode="after")
    def _reject_empty_order(self) -> "OrderCreate":
        if not self.items:
            raise ValueError("naročilo mora vsebovati vsaj eno postavko")
        return self


class OrderUpdate(BaseModel):
    """Vhodna shema za posodobitev statusa naročila."""

    status: OrderStatus


class Order(BaseModel):
    """Celoten domenski objekt naročila (poslovna shema)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    customer: Customer
    items: List[OrderItem]
    payment: Payment
    status: OrderStatus = OrderStatus.PENDING
    subtotal: Decimal = Field(..., ge=0, max_digits=14, decimal_places=2)
    shipping_fee: Decimal = Field(..., ge=0, max_digits=10, decimal_places=2)
    tax: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    total: Decimal = Field(..., gt=0, max_digits=14, decimal_places=2)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("subtotal", "shipping_fee", "tax", "total", mode="before")
    @classmethod
    def _round_amounts(cls, value: Any) -> Decimal:
        return money(value)

    @model_validator(mode="after")
    def _amounts_are_consistent(self) -> "Order":
        if self.total != (self.subtotal + self.shipping_fee + self.tax):
            raise ValueError("total mora biti vsota subtotal + shipping_fee + tax")
        return self
