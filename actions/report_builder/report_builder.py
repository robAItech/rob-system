"""report_builder — jedro domenske logike.

``build_report(csv_tekst)`` prebere CSV besedilo prek
``actions.csv_parser.parse_csv``, združi vrstice po stolpcu ``naslov``
(fallback: ``title``, nato prva vrednost v vrstici) in vrne
``dict {slug(naslov): [vrstice]}`` — ključe generira ``actions.string_ops.slug``.

Namerno brez Pydantic/async plasti v jedru (glej lekcijo string_ops):
preprosta čista funkcija = standardna knjižnica + obstoječi moduli.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - odvisno od postavitve paketa
    from actions.csv_parser import parse_csv
except ImportError:  # pragma: no cover
    from actions.csv_parser.parse_csv import parse_csv  # type: ignore

from actions.string_ops import slug
from actions.report_builder.markdown import render_report_as_markdown

TITLE_COLUMN = "naslov"
FALLBACK_TITLE_COLUMN = "title"


def _row_title(row: Any) -> Optional[str]:
    """Iz vrstice izlušči naslov: stolpec ``naslov`` → ``title`` → prva vrednost.

    Prazno zaporedje (``[]``, ``()``), ``None`` in vrstice brez uporabne
    vrednosti vrnejo ``None`` — nikoli stringifikacijo praznega objekta.
    """
    if isinstance(row, Mapping):
        for col in (TITLE_COLUMN, FALLBACK_TITLE_COLUMN):
            value = row.get(col)
            if value is not None and str(value).strip():
                return str(value).strip()
        for value in row.values():
            if value is not None and str(value).strip():
                return str(value).strip()
        return None
    if isinstance(row, (list, tuple)):
        if not row:
            return None
        first = row[0]
        if first is not None and str(first).strip():
            return str(first).strip()
        return None
    if row is None:
        return None
    text = str(row).strip()
    return text or None


def _normalize_rows(rows: List[Any]) -> List[Any]:
    """Poenoti izhod ``parse_csv``: dicti ali seznami z (prepoznano) header vrstico."""
    if not rows:
        return []
    if all(isinstance(r, Mapping) for r in rows):
        return rows
    if isinstance(rows[0], (list, tuple)):
        header = [str(c).strip() if c is not None else "" for c in rows[0]]
        if any(h.lower() in {TITLE_COLUMN, FALLBACK_TITLE_COLUMN} for h in header):
            return [dict(zip(header, r)) for r in rows[1:]]
    return rows


def build_report(csv_tekst: str) -> Dict[str, List[Any]]:
    """Zgradi poročilo iz CSV besedila.

    Args:
        csv_tekst: surovo CSV besedilo (z glavo; stolpec ``naslov`` določa
            naslov sekcije, po katerem se vrstice združijo).

    Returns:
        ``dict {slug(naslov): [vrstice]}``; vrstice ohranijo vrstni red iz CSV,
        ključi vrstni red prvega pojava naslova. Vrstice brez naslova se
        izpustijo.

    Raises:
        TypeError: če ``csv_tekst`` ni str.
        ValueError: če je ``csv_tekst`` None.
    """
    if csv_tekst is None:
        raise ValueError("csv_tekst ne sme biti None")
    if not isinstance(csv_tekst, str):
        raise TypeError("csv_tekst mora biti str")
    if not csv_tekst.strip():
        return {}

    raw = parse_csv(csv_tekst)
    rows = list(raw) if raw is not None else []

    report: Dict[str, List[Any]] = {}
    for row in _normalize_rows(rows):
        title = _row_title(row)
        if title is None:
            continue
        key = slug(title)
        report.setdefault(key, []).append(row)
    return report


async def build_report_async(csv_tekst: str) -> Dict[str, List[Any]]:
    """Async priročnica okoli ``build_report`` (čista async logika na vrhu)."""
    return build_report(csv_tekst)


def build_report_markdown(csv_tekst: str, title: str = "Poročilo") -> str:
    """Zgradi poročilo iz CSV in ga izpiše kot Markdown (output adapter).

    Konsolidacija observability plasti: Markdown izhod ni več samostojen Action
    (nekdanji ``markdown_summary``) — je adapter znotraj report_builderja.
    """
    return render_report_as_markdown(build_report(csv_tekst), title=title)