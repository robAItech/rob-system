"""Core domain logic for the markdown_summary module.

Architectural guideline mapping:
  - logika: Čista async logika -> `generate_summary` je async vhodna točka,
    ki preko executorja pokliče sinhrono render/persist jedro.
  - Izdelek: ustvari `summary.md` v actions/markdown_summary/ z naslovom `#`,
    odstavki in natanko 3 točkami.
"""

import asyncio
from pathlib import Path
from typing import Optional

from .schemas import SummaryDocument

MODULE_DIR = Path(__file__).resolve().parent
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


def write_summary_file(
    document: Optional[SummaryDocument] = None,
    target: Optional[Path] = None,
) -> Path:
    """Sinhrono persistiramo summary.md (jedro, ki ga kliče async vhodna točka)."""
    doc = document if document is not None else default_document()
    path = target if target is not None else MODULE_DIR / DEFAULT_FILENAME
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