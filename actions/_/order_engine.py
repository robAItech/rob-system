"""order_engine — čista poslovna logika naročil.

- ``round_money``: zaokroževanje po slovenskih pravilih (banker's rounding,
  polovične vrednosti k sodemu; zaokrožimo na 0,01).
- ``apply_discount``: progresivni popusti glede na količino (5/10/15 %).
- ``calculate_total``: 22 % DDV na neto znesek, zaokroženo na 0,01.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

#: 22 % DDV (Slovenija, standardna stopnja).
VAT_RATE: Decimal = Decimal("0.22")

#: Progresivni popusti: (minimalna količina, odstotek kot Decimal).
DISCOUNT_TIERS: tuple = (
    (50, Decimal("0.15")),  # >= 50 kosov -> 15 %
    (20, Decimal("0.10")),  # >= 20 kosov -> 10 %
    (10, Decimal("0.05")),  # >= 10 kosov -> 5 %
    (0, Decimal("0.00")),   # sicer 0 %
)

_DEC_2 = Decimal("0.01")


def _to_decimal(value: Any) -> Decimal:
    """Pretvori vrednost v Decimal; ``None``/prazno obravnava kot 0."""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Neveljavna številčna vrednost: {value!r}")
    if not dec.is_finite():
        raise ValueError(f"Neveljavna številčna vrednost: {value!r}")
    return dec


def round_money(x: Any) -> Decimal:
    """Zaokroži na 0,01 po slovenskih pravilih (banker's rounding, ROUND_HALF_EVEN)."""
    dec = _to_decimal(x)
    if dec.is_zero():
        return Decimal("0.00")
    return dec.quantize(_DEC_2, rounding=ROUND_HALF_EVEN)


def discount_rate(quantity: Any) -> Decimal:
    """Stopnja popusta (Decimal, npr. 0.15) glede na količino postavke."""
    try:
        qty = int(quantity)
    except (TypeError, ValueError):
        raise ValueError(f"Neveljavna količina: {quantity!r}")
    if qty < 0:
        raise ValueError(f"Količina ne sme biti negativna: {qty}")
    for threshold, rate in DISCOUNT_TIERS:
        if qty >= threshold:
            return rate
    return DISCOUNT_TIERS[-1][1]


def apply_discount(price: Any, qty: Any) -> Decimal:
    """Cena posamezne postavke po progresivnem popustu.

    Popust velja na ceno ENAKE postavke (količina istega SKU-ja), ne na
    celoten nakup: če qty >= 10 -> 5 %, qty >= 20 -> 10 %, qty >= 50 -> 15 %.
    Cena po popustu je zaokrožena na 0,01.
    """
    unit = _to_decimal(price)
    if unit < 0:
        raise ValueError(f"Cena ne sme biti negativna: {price!r}")
    rate = discount_rate(qty)
    discounted = unit * (Decimal("1") - rate)
    return round_money(discounted)


def calculate_total(items: Sequence[Mapping[str, Any]]) -> Decimal:
    """Skupni znesek naročila z 22 % DDV, zaokrožen na 0,01.

    Vsaka postavka (dict s ključi ``price`` in ``quantity``) se najprej
    diskontira s progresivnim popustom, nato se doda 22 % DDV na neto
    vrednost. Prazno naročilo vrne 0.00.
    """
    if items is None:
        return Decimal("0.00")
    net = Decimal("0")
    for item in items:
        unit = apply_discount(item.get("price", 0), item.get("quantity", 0))
        try:
            qty = int(item.get("quantity", 0))
        except (TypeError, ValueError):
            raise ValueError(f"Neveljavna količina: {item.get('quantity')!r}")
        if qty < 0:
            raise ValueError(f"Količina ne sme biti negativna: {qty}")
        net += unit * qty
    total = net * (Decimal("1") + VAT_RATE)
    return round_money(total)


def generate_order_id(index: int = 1) -> str:
    """Človeku prijazna številka naročila, npr. ORD-0001."""
    return f"ORD-{int(index):04d}"