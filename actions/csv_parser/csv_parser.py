"""Core CSV domain logic for the ``csv_parser`` module.

Pure stdlib implementation (no third-party dependencies) of CSV parsing and
serialization:

* ``parse_csv(text, delimiter=",")`` — razčleni CSV besedilo v seznam vrstic.
* ``to_csv(rows, delimiter=",")`` — pretvori seznam vrstic nazaj v CSV.

Funkciji sta inverzni: ``parse_csv(to_csv(rows)) == rows`` za dobro oblikovan
vhod (citiranje se uporabi, kjer je potrebno).
"""

from __future__ import annotations

import csv
import io
from typing import Any, List, Sequence


def parse_csv(text: str, delimiter: str = ",") -> List[List[str]]:
    """Razčleni CSV besedilo v seznam vrstic.

    Upošteva dvojne narekovaje (vključno z escaped ``""``), vgrajene
    delimiterje in vgrajene nove vrstice znotraj navedenih polj. Prazne
    vrstice so preskočene.

    Args:
        text: CSV besedilo, ki ga želimo razčleniti.
        delimiter: ločilni znak (privzeto ``","``); natanko en znak.

    Returns:
        Seznam vrstic; vsaka vrstica je seznam nizov (polj).

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
    # ``csv.reader`` za prazno vrstico vrne prazen seznam ``[]``; take vrstice
    # preskočimo, da rezultat vsebuje le dejanske podatkovne vrstice.
    return [list(row) for row in reader if row]


def to_csv(rows: Sequence[Sequence[Any]], delimiter: str = ",") -> str:
    """Pretvori seznam vrstic nazaj v CSV besedilo.

    Polja, ki vsebujejo delimiter, narekovaj ali novo vrstico, so ustrezno
    citirana, zato je rezultat inverzen :func:`parse_csv`. Vrednosti, ki niso
    nizi, so pretvorjene z :func:`str`.

    Args:
        rows: seznam vrstic; vsaka vrstica je seznam vrednosti.
        delimiter: ločilni znak (privzeto ``","``); natanko en znak.

    Returns:
        CSV besedilo brez končne nove vrstice.

    Raises:
        TypeError: če je ``rows`` ali ``delimiter`` ``None``.
        ValueError: če ``delimiter`` ni natanko en znak.
    """
    if rows is None:
        raise TypeError("rows ne sme biti None")
    if delimiter is None:
        raise TypeError("delimiter ne sme biti None")
    if not isinstance(delimiter, str) or len(delimiter) != 1:
        raise ValueError("delimiter mora biti natanko en znak")

    normalized: List[List[str]] = []
    for row in rows:
        normalized.append([cell if isinstance(cell, str) else str(cell) for cell in row])

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\n")
    writer.writerows(normalized)

    result = buffer.getvalue()
    if result.endswith("\n"):
        result = result[:-1]
    return result