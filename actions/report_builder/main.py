"""report_builder — FastAPI integracijski router.

Direktni JSONResponse handling za 4xx (neveljaven vhod) in 5xx (notranja
napaka); validacijo vhoda opravi Pydantic V2 (BuildReportRequest, strogo).
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from actions.report_builder.report_builder import build_report, build_report_markdown
from actions.report_builder.schemas import BuildReportRequest
from actions.report_builder.schemas import SummaryDocument
from actions.report_builder.markdown import render_markdown

router = APIRouter(prefix="/api/report-builder", tags=["report_builder"])


@router.post("/build")
async def build_report_endpoint(payload: BuildReportRequest) -> JSONResponse:
    """Zgradi poročilo iz CSV besedila; vrne ``{naslov_slug: [vrstice]}``."""
    if not payload.csv_tekst.strip():
        return JSONResponse(
            status_code=400, content={"detail": "csv_tekst ne sme biti prazen."}
        )
    try:
        report: Dict[str, List[Any]] = await run_in_threadpool(
            build_report, payload.csv_tekst
        )
    except (TypeError, ValueError) as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # pragma: no cover — zadnja obramba 5xx
        return JSONResponse(
            status_code=500, content={"detail": f"Notranja napaka: {exc}"}
        )
    return JSONResponse(content=report)


@router.post("/render")
async def render_report_endpoint(payload: BuildReportRequest) -> JSONResponse:
    """Zgradi poročilo iz CSV in ga vrne kot Markdown (output adapter)."""
    if not payload.csv_tekst.strip():
        return JSONResponse(
            status_code=400, content={"detail": "csv_tekst ne sme biti prazen."}
        )
    try:
        markdown: str = await run_in_threadpool(build_report_markdown, payload.csv_tekst)
    except (TypeError, ValueError) as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # pragma: no cover — zadnja obramba 5xx
        return JSONResponse(
            status_code=500, content={"detail": f"Notranja napaka: {exc}"}
        )
    return JSONResponse(content={"markdown": markdown})


@router.post("/render-summary")
async def render_summary_endpoint(document: SummaryDocument) -> JSONResponse:
    """Render SummaryDocument (nekdanji markdown_summary) v Markdown."""
    return JSONResponse(content={"markdown": render_markdown(document)})