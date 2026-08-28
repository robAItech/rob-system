"""Core Domain Logic — finančni izračuni (finance_calc).

Čiste, brezstranske funkcije za finančne izračune:

* ``vat_price``      — cena z DDV (npr. ``vat_price(100, 0.22) == 122.0``);
* ``discount_price`` — cena s popustom (npr. ``discount_price(100, 10) == 90.0``);
* ``format_eur``     — znesek v EUR po slovenski konvenciji
  (npr. ``format_eur(1234567.89) == '1.234.567,89 EUR'``);
* ``cagr``           — sestavljena letna rast (CAGR) v odstotkih.
"""

from __future__ import annotations

import math

__all__ = ["vat_price", "discount_price", "format_eur", "cagr"]


def _round2(value: float) -> float:
    """Zaokroži na 2 decimalki in normalizira ``-0.0`` na ``0.0``."""
    rounded = round(float(value), 2)
    return 0.0 if rounded == 0 else rounded


def vat_price(price: float, rate: float = 0.22) -> float:
    """Cena z DDV, zaokrožena na 2 decimalki.

    Args:
        price: neto cena.
        rate: DDV stopnja (npr. 0.22 za 22 %).

    Returns:
        Bruto cena (``price * (1 + rate)``), zaokrožena na 2 decimalki.
    """
    return _round2(price * (1.0 + rate))


def discount_price(price: float, percent: float) -> float:
    """Cena s popustom, zaokrožena na 2 decimalki.

    Args:
        price: prvotna cena.
        percent: popust v odstotkih, obvezno v intervalu [0, 100].

    Returns:
        Cena po popustu (``price * (1 - percent / 100)``),
        zaokrožena na 2 decimalki.

    Raises:
        ValueError: če ``percent`` ni v intervalu [0, 100].
    """
    percent = float(percent)
    if not 0.0 <= percent <= 100.0:
        raise ValueError("percent mora biti med 0 in 100")
    return _round2(price * (1.0 - percent / 100.0))


def format_eur(value: float) -> str:
    """Oblikuj znesek v EUR niz po slovenski konvenciji.

    Pravila:
      * cela števila brez decimalk:        5          -> '5 EUR'
      * dve decimalki z vejico:            5.5        -> '5,50 EUR'
      * tisočice ločene s piko:            1234567.89 -> '1.234.567,89 EUR'
      * negativni znesek ima predznak:    -5.5        -> '-5,50 EUR'

    Args:
        value: znesek v EUR (float ali karkoli pretvorljivega v float).

    Returns:
        Oblikovan EUR niz.

    Raises:
        ValueError: če vrednost ni število ali ni končna (NaN/inf).
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"znesek ni število: {value!r}") from None
    if not math.isfinite(v):
        raise ValueError("znesek mora biti končno število")

    negative = v < 0
    total_cents = int(round(abs(v) * 100))
    whole, cents = divmod(total_cents, 100)
    sign = "-" if negative else ""
    number = f"{whole:,}".replace(",", ".")
    if cents == 0:
        return f"{sign}{number} EUR"
    return f"{sign}{number},{cents:02d} EUR"


def cagr(values: list[float]) -> float:
    """Sestavljena letna rast (CAGR) v odstotkih, zaokrožena na 2 decimalki.

    Args:
        values: seznam letnih vrednosti (npr. prihodkov po letih).

    Returns:
        CAGR v %: ``((last / first) ** (1 / (n - 1)) - 1) * 100``.
        Prazen ali enoelementni seznam vrne ``0.0``; nedefinirane baze
        (0 ali negativne vrednosti) prav tako vrnejo ``0.0``.
    """
    if not values or len(values) < 2:
        return 0.0
    first = float(values[0])
    last = float(values[-1])
    if first <= 0.0 or last <= 0.0:
        return 0.0
    periods = len(values) - 1
    ratio = last / first
    if ratio <= 0.0:
        return 0.0
    return _round2((ratio ** (1.0 / periods) - 1.0) * 100.0)