"""Jedrna logika modula iso8601_util.

Čiste, sinhrone funkcije brez zunanjih odvisnosti (samo standardna knjižnica):

- ``parse_iso(niz)`` : razčleni ISO 8601 datum (YYYY-MM-DD) v ``datetime``
  (ob polnoči, 00:00:00).
- ``format_iso(dt)`` : oblikuje ``datetime``/``date`` nazaj v niz "YYYY-MM-DD".
"""

from __future__ import annotations

import re
from datetime import date, datetime

__all__ = ["parse_iso", "format_iso"]

# Stroga oblika: natanko YYYY-MM-DD z vodilnimi ničlami (brez presledkov,
# brez časa, brez časovnega pasu).
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso(niz: str) -> datetime:
    """Razčleni ISO 8601 datum (YYYY-MM-DD) v ``datetime`` ob polnoči.

    Args:
        niz: Datumski niz v obliki YYYY-MM-DD, npr. ``"2024-01-15"``.

    Returns:
        ``datetime`` z urami/minutami/sekundami na 0.

    Raises:
        ValueError: Če vhod ni veljaven datum v obliki YYYY-MM-DD
            (napačen format, neobstoječ mesec/dan, neprestopno leto,
            prazen niz, ``None`` itd.).
    """
    if not isinstance(niz, str) or not _ISO_DATE_RE.match(niz):
        raise ValueError(
            f"Neveljaven ISO 8601 datum: {niz!r} (pričakovan format YYYY-MM-DD)"
        )
    try:
        return datetime.strptime(niz, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Neveljaven ISO 8601 datum: {niz!r}") from None


def format_iso(dt) -> str:
    """Oblikuje ``datetime`` (ali ``date``) v ISO 8601 niz "YYYY-MM-DD".

    Args:
        dt: ``datetime`` ali ``date``. Časovna komponenta se izpusti.

    Returns:
        Niz v obliki YYYY-MM-DD, npr. ``"2024-01-15"``.

    Raises:
        TypeError: Če vhod ni ``datetime``/``date``.
    """
    if not isinstance(dt, (datetime, date)):
        raise TypeError(
            f"Pričakovan datetime ali date, dobil {type(dt).__name__!r}"
        )
    return dt.strftime("%Y-%m-%d")
