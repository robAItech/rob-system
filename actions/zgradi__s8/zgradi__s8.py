"""zgradi__s8 — jedrna domena.

Čista async logika za generiranje Markdown poročila z arhitekturo,
uporabo in navodili za zagon. Plast ne odvisi od spleta; HTTP skrb
plast main.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .schemas import ReportRequest, ReportResponse, ReportSection

DEFAULT_REPORT_FILENAME = "README.md"

_DEFAULT_TITLE = "zgradi__s8 — Markdown Report Builder"
_DEFAULT_SECTIONS = (
    (
        "Arhitektura",
        "Modul je sestavljen iz shem (Pydantic V2 s strogimi validatorji), "
        "čiste async jedrne logike (zgradi__s8.py) in FastAPI vmesnika "
        "(main.py) z direktnim JSONResponse 4xx/5xx handlingom.",
    ),
    (
        "Uporaba",
        "Pokliči `generate_report()` z `ReportRequest` (ali dict) in dobiš "
        "`ReportResponse` z Markdown vsebino; prek HTTP pošlji POST na "
        "`/api/v1/reports`.",
    ),
    (
        "Navodila za zagon",
        "Namesti `fastapi`, `uvicorn`, `pydantic`; zaženi "
        "`uvicorn zgradi__s8.main:app --reload`; preveri `/api/v1/health`; "
        "poženi `pytest -q`.",
    ),
)


def render_markdown(request: Union[ReportRequest, dict]) -> str:
    """Sestavi Markdown niz iz validirane zahteve (model ali dict)."""
    req = (
        request
        if isinstance(request, ReportRequest)
        else ReportRequest.model_validate(request)
    )
    lines: list[str] = [f"# {req.title}", ""]
    for section in req.sections:
        lines.append(f"## {section.title}")
        lines.append("")
        lines.append(section.body.strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


async def generate_report(
    request: Union[ReportRequest, dict],
    filename: str = DEFAULT_REPORT_FILENAME,
    output_dir: Optional[Path] = None,
) -> ReportResponse:
    """Async generiranje Markdown poročila; opcijsko zapis na disk.

    Če ``output_dir`` ni podan, poročilo ni zapisano — samo vrnjeno.
    """
    markdown = render_markdown(request)
    response = ReportResponse(filename=filename, markdown=markdown)
    if output_dir is not None:
        target_dir = Path(output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / filename).write_text(markdown, encoding="utf-8")
    return response


async def build_default_report(filename: str = DEFAULT_REPORT_FILENAME) -> ReportResponse:
    """Async generiranje privzetega poročila (arhitektura, uporaba, zagon)."""
    request = ReportRequest(
        title=_DEFAULT_TITLE,
        sections=[
            ReportSection(title=title, body=body) for title, body in _DEFAULT_SECTIONS
        ],
    )
    return await generate_report(request, filename=filename)