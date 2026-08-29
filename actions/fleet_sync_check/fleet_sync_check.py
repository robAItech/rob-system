"""Core Domain Logic for fleet_sync_check.

Minimalni modul: funkcija ``add2`` vrne vsoto dveh vrednosti.
Float rezultati so zaokroženi na 10 decimalk, da se izognemo
artefaktom IEEE-754 aritmetike (npr. 0.1 + 0.2 == 0.3).
"""

from __future__ import annotations

from typing import Union

Numeric = Union[int, float]

# Število decimalk za normalizacijo float rezultatov.
_FLOAT_PRECISION = 10


def add2(a: Numeric, b: Numeric) -> Numeric:
    """Vrni vsoto ``a + b``.

    Args:
        a: prvi operand (int ali float).
        b: drugi operand (int ali float).

    Returns:
        Vsota ``a + b``; tip rezultata sledi Pythonovi aritmetiki
        (int + int -> int, sicer float). Float rezultati so zaokroženi
        na 10 decimalk, kar zagotovi npr. ``add2(0.1, 0.2) == 0.3``.
    """
    result = a + b
    if isinstance(result, float):
        return round(result, _FLOAT_PRECISION)
    return result