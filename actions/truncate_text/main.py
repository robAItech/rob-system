"""FastAPI Integration Router — HTTP vmesnik za modul truncate_text."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .schemas import TruncateRequest, TruncateResponse
from .truncate_text import truncate

router = APIRouter(prefix="/truncate", tags=["truncate"])


@router.post("", response_model=TruncateResponse)
async def truncate_text(payload: TruncateRequest) -> TruncateResponse:
    """Skrajša niz iz telesa zahteve."""
    try:
        result = truncate(payload.niz, payload.max_len, payload.suffix)
    except Exception as exc:  # pragma: no cover — obrambno
        return JSONResponse(
            status_code=500, content={"detail": f"Napaka pri obdelavi: {exc}"}
        )
    return TruncateResponse(
        result=result,
        truncated=result != payload.niz,
        original_length=len(payload.niz),
    )


@router.get("", response_model=TruncateResponse)
async def truncate_text_get(
    niz: str, max_len: int = 80, suffix: str = "..."
) -> TruncateResponse:
    """Skrajša niz iz query parametrov (priročno za hitre klice)."""
    result = truncate(niz, max_len, suffix)
    return TruncateResponse(
        result=result,
        truncated=result != niz,
        original_length=len(niz),
    )


app = FastAPI(title="truncate_text API", version="1.0.0")
app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Direkten JSON 4xx odziv za neveljavne vhode."""
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Direkten JSON 5xx odziv za nepričakovane napake."""
    return JSONResponse(
        status_code=500, content={"detail": "Nepričakovana napaka strežnika"}
    )