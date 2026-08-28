"""data_format_utils.formats — konsolidirane formatne funkcije (Refaktor 3).

Arhitekturna revizija (2026): nekdanji `csv_parser`, `iso8601_util` in
`json_deep_merge` so konsolidirani v EN modul. Tu živi vsa logika:
  - ``parse_csv`` / ``to_csv``      (nekoč actions.csv_parser),
  - ``parse_iso`` / ``format_iso``  (nekoč actions.iso8601_util),
  - ``deep_merge``                  (nekoč actions.json_deep_merge).

Stari moduli so zdaj tanke fasade, ki re-exportajo od tod. Vse funkcije so
čiste in uporabljajo samo standardno knjižnico.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any, List, Sequence

# ── CSV (nekoč actions.csv_parser) ──────────────────────────────────────────
__all__ = ["parse_csv", "to_csv", "parse_iso", "format_iso", "deep_merge"]


def parse_csv(text: str, delimiter: str = ",") -> List[List[str]]:
    """Razčleni CSV besedilo v seznam vrstic (citiranje, vgrajeni delimiterji).

    Args:
        text: CSV besedilo; ``None`` → TypeError.
        delimiter: ločilni znak, natanko en znak.

    Raises:
        TypeError: če je ``text`` ali ``delimiter`` ``None``.
        ValueError: če ``delimiter`` ni natanko en znak.
    """
    if text is None:
        raise TypeError("text ne sme biti None")
    if delimiter is None:
        raise TypeError("delimiter ne sme biti None")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ValueError("delimiter mora biti natanko en znak")
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return [list(row) for row in reader if row]


def to_csv(rows: Sequence[Sequence[Any]], delimiter: str = ",") -> str:
    """Pretvori seznam vrstic nazaj v CSV (inverzno ``parse_csv``)."""
    if rows is None:
        raise TypeError("rows ne sme biti None")
    if delimiter is None:
        raise TypeError("delimiter ne sme biti None")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ValueError("delimiter mora biti natanko en znak")
    normalized: List[List[str]] = [
        [cell if isinstance(cell, str) else str(cell) for cell in row] for row in rows
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerows(normalized)
    result = buffer.getvalue()
    return result[:-1] if result.endswith("\n") else result


# ── ISO 8601 (nekoč actions.iso8601_util) ───────────────────────────────────
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_iso(niz: str) -> datetime:
    """Razčleni ISO 8601 datum (YYYY-MM-DD) v ``datetime`` ob polnoči.

    Raises:
        ValueError: če vhod ni veljaven datum YYYY-MM-DD.
    """
    if not isinstance(niz, str) or not _ISO_DATE_RE.match(niz):
        raise ValueError(
            f"Neveljaven ISO 8601 datum: {niz!r} (pričakovan format YYYY-MM-DD)"
        )
    try:
        return datetime.strptime(niz, "%Y-%m-%d")
    except ValueError:
        raise ValueError(
            f"Neveljaven ISO 8601 datum: {niz!r} (neobstoječ datum ali nepravilna vrednost)"
        )


def format_iso(dt: "date | datetime") -> str:
    """Oblikuj ``datetime``/``date`` v ISO 8601 niz YYYY-MM-DD."""
    if not isinstance(dt, (date, datetime)):
        raise TypeError(f"format_iso pričakuje date/datetime, dobil {type(dt).__name__}")
    return dt.strftime("%Y-%m-%d")


# ── Deep merge (nekoč actions.json_deep_merge) ──────────────────────────────
def deep_merge(a: Any, b: Any) -> Any:
    """Rekurzivno združi ``b`` v ``a`` (dict→rekurzivno, list→združi, scalar→b).

    Vhodnih struktur ne mutira; vrne novo združeno strukturo.
    """
    if isinstance(a, dict) and isinstance(b, dict):
        merged: dict[Any, Any] = {}
        for key in set(a) | set(b):
            if key in a and key in b:
                merged[key] = deep_merge(a[key], b[key])
            else:
                merged[key] = a[key] if key in a else b[key]
        return merged
    if isinstance(a, list) and isinstance(b, list):
        return list(a) + list(b)
    return b
