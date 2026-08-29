"""FastAPI Integration Router — streže Q3 Markdown poročilo."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse, PlainTextResponse

from .q3_report import default_data, generate_q3_report, render_report
from .schemas import Q3ReportData

router = APIRouter(prefix="/q3-report", tags=["q3-report"])


@router.get("/report")
async def get_report() -> JSONResponse:
    """Vrni Q3 poročilo kot JSON (naslov + Markdown vsebina)."""
    try:
        markdown = await generate_q3_report()
        return JSONResponse(
            status_code=200,
            content={"title": "Poročilo o rezultatih Q3", "markdown": markdown},
        )
    except Exception as exc:  # pragma: no cover
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.get("/report.md")
async def get_report_markdown() -> PlainTextResponse:
    """Vrni Q3 poročilo neposredno kot Markdown dokument."""
    try:
        markdown = await generate_q3_report()
        return PlainTextResponse(content=markdown, media_type="text/markdown")
    except Exception as exc:  # pragma: no cover
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/report")
async def build_report(data: Q3ReportData) -> JSONResponse:
    """Sestavi Markdown poročilo iz posredovanih podatkov (analiza + povzetek)."""
    markdown = render_report(data)
    return JSONResponse(status_code=200, content={"markdown": markdown})