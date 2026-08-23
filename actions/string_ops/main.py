"""FastAPI Integration Router — HTTP vmesnik za modul string_ops.

Vsi endpointi vračajo ``JSONResponse`` neposredno: uspeh -> 200,
``TypeError`` (ne-str vhod) -> 400, nepričakovana napaka -> 500.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .schemas import (
    NormalizeRequest,
    SlugRequest,
    TokenizeRequest,
    TruncateRequest,
    TruncateStartRequest,
    WordFreqRequest,
)
from .string_ops import (
    normalize,
    slug,
    tokenize,
    truncate,
    truncate_start,
    word_freq,
)

router = APIRouter(prefix="/string-ops", tags=["string_ops"])


def _napaka(exc: Exception) -> JSONResponse:
    """4xx/5xx JSONResponse handling: TypeError -> 400, ostalo -> 500."""
    if isinstance(exc, TypeError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/slug")
async def slug_endpoint(payload: SlugRequest) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content={"slug": slug(payload.text)})
    except Exception as exc:  # pragma: no cover - defensivno
        return _napaka(exc)


@router.post("/truncate")
async def truncate_endpoint(payload: TruncateRequest) -> JSONResponse:
    try:
        result = truncate(payload.text, max_len=payload.max_len, suffix=payload.suffix)
        return JSONResponse(status_code=200, content={"result": result})
    except Exception as exc:  # pragma: no cover - defensivno
        return _napaka(exc)


@router.post("/truncate-start")
async def truncate_start_endpoint(payload: TruncateStartRequest) -> JSONResponse:
    try:
        result = truncate_start(payload.text, max_len=payload.max_len, prefix=payload.prefix)
        return JSONResponse(status_code=200, content={"result": result})
    except Exception as exc:  # pragma: no cover - defensivno
        return _napaka(exc)


@router.post("/tokenize")
async def tokenize_endpoint(payload: TokenizeRequest) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content={"words": tokenize(payload.text)})
    except Exception as exc:  # pragma: no cover - defensivno
        return _napaka(exc)


@router.post("/normalize")
async def normalize_endpoint(payload: NormalizeRequest) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content={"result": normalize(payload.text)})
    except Exception as exc:  # pragma: no cover - defensivno
        return _napaka(exc)


@router.post("/word-freq")
async def word_freq_endpoint(payload: WordFreqRequest) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content={"frequencies": word_freq(payload.text)})
    except Exception as exc:  # pragma: no cover - defensivno
        return _napaka(exc)
