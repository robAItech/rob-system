"""FastAPI integracijski router za modul iso8601_util.

Endpointa:
    GET  /iso8601/health          — preverjanje delovanja
    POST /iso8601/parse           — "2024-01-15" -> "2024-01-15T00:00:00"
    POST /iso8601/format          — "2024-01-15T10:30:00" -> "2024-01-15"

Napake se vračajo kot direktni `JSONResponse` s 4xx/5xx statusi:
    - 422 za shemo/validacijo (Pydantic ValidationError),
    - 400 za logične napake jedra (ValueError),
    - 500 za nepričakovane izjeme (TypeError, Exception).
"""

from datetime import datetime

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .core import format_iso, parse_iso
from .schemas import IsoDateRequest, IsoDateTimeRequest, IsoDateResponse

router = APIRouter(prefix="/iso8601", tags=["iso8601"])


@router.get("/health")
async def health() -> JSONResponse:
    """Preveri, da je modul živo in da jedro deluje."""
    try:
        parse_iso("2024-01-15")
    except Exception as exc:  # pragma: no cover - obramba pred pokvarjenim okoljem
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(exc)})
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.post("/parse", response_model=IsoDateResponse)
async def parse_endpoint(request: IsoDateRequest) -> JSONResponse:
    """Razčleni ISO 8601 datum v datetime (polnoč) in ga vrni kot ISO niz."""
    try:
        parsed: datetime = parse_iso(request.value)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # pragma: no cover - nepričakovana napaka jedra
        return JSONResponse(status_code=500, content={"detail": f"internal error: {exc}"})
    return JSONResponse(status_code=200, content=IsoDateResponse(value=parsed.isoformat()).model_dump())


@router.post("/format", response_model=IsoDateResponse)
async def format_endpoint(request: IsoDateTimeRequest) -> JSONResponse:
    """Oblikuj datetime (ali datum) nazaj v ISO 8601 niz YYYY-MM-DD."""
    try:
        dt = datetime.fromisoformat(request.value)
        formatted: str = format_iso(dt)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except TypeError as exc:  # pragma: no cover - obramba pred napačnim tipom
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # pragma: no cover - nepričakovana napaka
        return JSONResponse(status_code=500, content={"detail": f"internal error: {exc}"})
    return JSONResponse(status_code=200, content=IsoDateResponse(value=formatted).model_dump())


app = FastAPI(title="iso8601_util", version="1.0.0")
app.include_router(router)