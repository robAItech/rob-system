"""Jedro modula iso8601_util: čista logika za ISO 8601 datumsko pretvorbo.

Po arhitekturni smernici (in konsolidirani lekciji iz slugify) jedro uporablja
zgolj standardno knjižnico `datetime` — brez Pydantic/async plasti, saj sta
`parse_iso` in `format_iso` preprosti, čisti in sinhroni funkciji.

Format: YYYY-MM-DD (ISO 8601 osnovna datumovska oblika).
"""

from datetime import date, datetime
from typing import Union


def parse_iso(value: str) -> datetime:
    """Razčleni ISO 8601 datum (YYYY-MM-DD) v `datetime` (ob polnoči).

    Args:
        value: niz oblike `YYYY-MM-DD`, npr. `"2024-01-15"`.

    Returns:
        `datetime` z urami/minutami/sekundami na 0 (polnoč).

    Raises:
        ValueError: če `value` ni veljaven ISO 8601 datum `YYYY-MM-DD`
            (napačna oblika, neobstoječ datum, napačen tip ali prazen niz).
    """
    if not isinstance(value, str):
        raise ValueError(
            f"parse_iso pričakuje niz, dobil {type(value).__name__}: {value!r}"
        )
    stripped = value.strip()
    if stripped != value:
        raise ValueError(f"neveljaven ISO 8601 datum (vodilni/sledeči presledki): {value!r}")
    if len(stripped) != 10:
        raise ValueError(f"neveljaven ISO 8601 datum (pričakovana dolžina 10): {value!r}")

    # Strogo preveri ločila, da ne sprejmemo npr. "2024/01/15" ali "2024-1-5".
    if stripped[4] != "-" or stripped[7] != "-":
        raise ValueError(f"neveljaven ISO 8601 datum (napačna ločila): {value!r}")

    try:
        year, month, day = (int(part) for part in stripped.split("-"))
    except ValueError:
        raise ValueError(f"neveljaven ISO 8601 datum (nedigitalne komponente): {value!r}") from None

    # `date` sam opravi strogo preverjanje (leto 1..9999, mesec 1..12,
    # dan 1..dni v mesecu, vključno s prestopnimi leti).
    try:
        parsed = date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"neveljaven ISO 8601 datum: {value!r} ({exc})") from None

    return datetime(parsed.year, parsed.month, parsed.day)


def format_iso(dt: Union[datetime, date]) -> str:
    """Oblikuj `datetime` (ali `date`) nazaj v ISO 8601 niz `YYYY-MM-DD`.

    Ure, minute in sekunde se zavržejo — izhod je zgolj datumski del.

    Args:
        dt: `datetime` ali `date` objekt.

    Returns:
        Niz oblike `YYYY-MM-DD`, npr. `"2024-01-15"`.

    Raises:
        TypeError: če `dt` ni `datetime` ali `date`.
    """
    if not isinstance(dt, (datetime, date)):
        raise TypeError(
            f"format_iso pričakuje datetime|date, dobil {type(dt).__name__}: {dt!r}"
        )
    return dt.strftime("%Y-%m-%d")