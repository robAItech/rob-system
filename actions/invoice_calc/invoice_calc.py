"""Čista logika (async) za izračun faktur z DDV in popusti.

Podprti so tako odstotki (22 → 22 %) kot ulomki (0.22 → 22 %); normalizacija
poteka v `_normalize_rate`. Vse denarne vrednosti se obdelujejo z Decimal in
zaokrožijo na 2 decimalki (ROUND_HALF_UP) šele v rezultatu.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Iterable, Optional, Union

from .schemas import (
    InvoiceItem,
    InvoiceRequest,
    InvoiceResult,
    round_money,
    to_decimal,
)

__all__ = [
    "InvoiceValidationError",
    "calculate_invoice",
    "calculate_total",
    "compute_invoice",
    "compute_total",
    "round_money",
    "to_decimal",
]


class InvoiceValidationError(ValueError):
    """Napaka pri logični validaciji vhodnih podatkov za izračun fakture."""


def _normalize_rate(value: Any, field: str) -> Decimal:
    """Normalizira stopnjo: odstotek (22) ali ulomek (0.22) → ulomek (0.22)."""
    rate = to_decimal(value)
    if rate < 0:
        raise InvoiceValidationError(f"{field} ne sme biti negativen")
    if rate > 1:
        rate = rate / Decimal("100")
    return rate


def _resolve_request(
    request: Optional[Union[InvoiceRequest, Dict[str, Any]]],
    items: Optional[Iterable[Union[InvoiceItem, Dict[str, Any]]]],
    vat_rate: Any,
    discount_percent: Any,
    discount: Any,
    vat: Any,
    currency: str,
) -> InvoiceRequest:
    if request is not None:
        if isinstance(request, InvoiceRequest):
            return request
        if isinstance(request, dict):
            return InvoiceRequest.model_validate(request)
        raise TypeError("request mora biti InvoiceRequest, dict ali None")
    if discount_percent is None:
        discount_percent = discount if discount is not None else Decimal("0")
    if vat_rate is None:
        vat_rate = vat if vat is not None else Decimal("0")
    if items is None:
        raise InvoiceValidationError("manjkajo postavke fakture (items)")
    return InvoiceRequest(
        items=list(items),
        vat_rate=vat_rate,
        discount_percent=discount_percent,
        currency=currency,
    )


def _calculate(req: InvoiceRequest) -> InvoiceResult:
    """Sinhrono jedro izračuna — brez stranskih učinkov, čisto."""
    vat_rate = _normalize_rate(req.vat_rate, "vat_rate")
    global_discount = _normalize_rate(req.discount_percent, "discount_percent")

    subtotal = Decimal("0")
    discount_amount = Decimal("0")
    for item in req.items:
        line_total = item.quantity * item.unit_price
        subtotal += line_total
        line_discount = _normalize_rate(item.discount_percent, "discount_percent")
        discount_amount += line_total * line_discount

    discount_amount += subtotal * global_discount
    if discount_amount > subtotal:
        discount_amount = subtotal

    taxable_amount = subtotal - discount_amount
    vat_amount = taxable_amount * vat_rate
    total = taxable_amount + vat_amount

    return InvoiceResult(
        currency=req.currency,
        item_count=len(req.items),
        subtotal=round_money(subtotal),
        discount_amount=round_money(discount_amount),
        taxable_amount=round_money(taxable_amount),
        vat_amount=round_money(vat_amount),
        total=round_money(total),
    )


async def calculate_invoice(
    request: Optional[Union[InvoiceRequest, Dict[str, Any]]] = None,
    *,
    items: Optional[Iterable[Union[InvoiceItem, Dict[str, Any]]]] = None,
    vat_rate: Any = None,
    discount_percent: Any = None,
    currency: str = "EUR",
    discount: Any = None,
    vat: Any = None,
) -> InvoiceResult:
    """Izračuna fakturo z DDV in popusti (async vstopna točka).

    Sprejme `InvoiceRequest`, dict ali posamezne argumente (`items`, `vat_rate`,
    `discount_percent`/`discount`, `vat`, `currency`).
    """
    req = _resolve_request(
        request, items, vat_rate, discount_percent, discount, vat, currency
    )
    return _calculate(req)


def compute_invoice(
    request: Optional[Union[InvoiceRequest, Dict[str, Any]]] = None,
    *,
    items: Optional[Iterable[Union[InvoiceItem, Dict[str, Any]]]] = None,
    vat_rate: Any = None,
    discount_percent: Any = None,
    currency: str = "EUR",
    discount: Any = None,
    vat: Any = None,
) -> InvoiceResult:
    """Sinhronska različica `calculate_invoice` (za teste in preproste klice)."""
    req = _resolve_request(
        request, items, vat_rate, discount_percent, discount, vat, currency
    )
    return _calculate(req)


async def calculate_total(
    request: Optional[Union[InvoiceRequest, Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Decimal:
    """Vrne samo končni znesek fakture (skupaj z DDV)."""
    result = await calculate_invoice(request, **kwargs)
    return result.total


def compute_total(
    request: Optional[Union[InvoiceRequest, Dict[str, Any]]] = None,
    **kwargs: Any,
) -> Decimal:
    """Sinhronska različica `calculate_total`."""
    return compute_invoice(request, **kwargs).total
