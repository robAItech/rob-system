"""report_builder — Markdown izhodni adapter.

Arhitekturna konsolidacija (2.3): nekdanji samostojni ``actions.markdown_summary``
je absorbiran kot **output driver/adapter** prezentačijske plasti report_builder.
Tukaj so: ``SummaryDocument`` shema (v schemas.py), render v Markdown in
generiranje datoteke — brez samostojnega Action modula.

Logika:
  - ``render_markdown(document)`` — H1 naslov, odstavki, natanko 3 točke.
  - ``write_summary_file(document, target)`` — sinhrono persistiramo ``summary.md``.
  - ``generate_summary(document, target)`` — čista async vhodna točka (I/O v executor).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from .schemas import SummaryDocument

DEFAULT_FILENAME = "summary.md"


def default_document() -> SummaryDocument:
    """Privzeti dokument: kratek povzetek prednosti avtonomnega AI inženirstva."""
    return SummaryDocument(
        title="Prednosti avtonomnega AI inženirstva",
        paragraphs=[
            "Avtonomno AI inženirstvo združuje sodobne jezikovne modele s "
            "samodejnimi povratnimi zankami, ki načrtujejo, pišejo, testirajo in "
            "izboljšujejo programsko opremo z minimalnim človeškim posredovanjem. "
            "Namesto enkratnega izpisa kode vodi celoten življenjski cikel razvoja — "
            "od specifikacije in pregleda do uvajanja in učenja iz napak.",
            "Tak pristop skrajša čas od ideje do delujoče rešitve in poveča "
            "zanesljivost, saj vsak neuspeh postane podatek za izboljšavo, ne le "
            "napaka, ki jo je treba ročno odpraviti.",
        ],
        bullet_points=[
            "Hitrost in produktivnost: avtomatizacija rutinskih opravil sprosti "
            "inženirje za kompleksnejše odločitve.",
            "Kakovost in zanesljivost: vgrajene povratne zanke (testi, pregledi, "
            "evalvacije) sistematično lovijo napake pred produkcijo.",
            "Neprekinjeno učenje: vsak neuspeh in vsaka lekcija se konsolidirata "
            "v ponovno uporabno znanje, ki izboljšuje vse prihodnje naloge.",
        ],
    )


def render_markdown(document: SummaryDocument) -> str:
    """Render SummaryDocument v Markdown: H1 naslov, odstavki, 3 točke."""
    lines: list[str] = [f"# {document.title}", ""]
    for paragraph in document.paragraphs:
        lines.append(paragraph)
        lines.append("")
    for point in document.bullet_points:
        lines.append(f"- {point}")
    return "\n".join(lines).rstrip() + "\n"


def render_report_as_markdown(report: dict, title: str = "Poročilo") -> str:
    """Render že zgrajenega poročila (``{slug: [vrstice]}``) v Markdown.

    Vsaka sekcija poročila postane ``## <naslov>``; vrstice se izpišejo kot
    ``- <prva vrednost>``. Tako isti report_builder, ki gradi ``build_report``,
    izpiše tudi Markdown izhod — brez ločenega modula.
    """
    lines: list[str] = [f"# {title}", ""]
    for slug, rows in report.items():
        lines.append(f"## {slug}")
        lines.append("")
        for row in rows:
            lines.append(f"- {_row_label(row)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _row_label(row) -> str:
    """Človeku berljiva oznaka vrstice (prva vrednost dict/lista)."""
    if isinstance(row, dict):
        for value in row.values():
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""
    if isinstance(row, (list, tuple)) and row:
        return str(row[0]).strip() if row[0] is not None else ""
    return str(row).strip()


def write_summary_file(
    document: Optional[SummaryDocument] = None,
    target: Optional[Path] = None,
) -> Path:
    """Sinhrono persistiramo summary.md (jedro, ki ga kliče async vhodna točka)."""
    doc = document if document is not None else default_document()
    path = target if target is not None else Path("summary.md")
    path.write_text(render_markdown(doc), encoding="utf-8")
    return path


async def generate_summary(
    document: Optional[SummaryDocument] = None,
    target: Optional[Path] = None,
) -> Path:
    """Čista async vhodna točka: generira in shrani Markdown dokument.

    Blokirajočo I/O (pisanje datoteke) premaknemo v executor, da ne zamašimo
    event loop-a.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, write_summary_file, document, target)
