"""zgradi__s8 — FastAPI integracijski router.

API plast: HTTP vmesnik za generiranje Markdown poročil z direktnim
JSONResponse handlingom za 4xx (422) in 5xx (500) napake.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from .schemas import ReportRequest
from .zgradi__s8 import DEFAULT_REPORT_FILENAME, generate_report

router = APIRouter(prefix="/api/v1", tags=["zgradi__s8"])


@router.post("/reports")
async def create_report(payload: ReportRequest) -> JSONResponse:
    """Generira Markdown poročilo iz validiranega vhoda (JSON body)."""
    try:
        report = await generate_report(payload, filename=DEFAULT_REPORT_FILENAME)
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})
    except Exception as exc:  # noqa: BLE001 — nepričakovana napaka -> 500
        return JSONResponse(
            status_code=500,
            content={"detail": f"Napaka pri generiranju poročila: {exc}"},
        )
    return JSONResponse(status_code=200, content=report.model_dump())


@router.get("/health")
async def health() -> JSONResponse:
    """Preveri delovanje API-ja."""
    return JSONResponse(status_code=200, content={"status": "ok"})


app = FastAPI(
    title="zgradi__s8",
    version="1.0.0",
    description="Markdown Report Builder — arhitektura, uporaba, navodila za zagon.",
)
app.include_router(router)