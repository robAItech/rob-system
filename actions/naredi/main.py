"""FastAPI Integration Router — finance_calc API.

HTTP izpostavitev čistih funkcij modula `naredi` z direktnim
JSONResponse 4xx/5xx handlingom (brez dviganja HTTPException).
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

try:
    from .naredi import cagr, discount_price, format_eur, vat_price
    from .schemas import (
        CagrRequest,
        CagrResponse,
        DiscountPriceRequest,
        EurResponse,
        FormatEurRequest,
        PriceResponse,
        VatPriceRequest,
    )
except ImportError:  # pragma: no cover — fallback za direktni uvoz modula
    from naredi import cagr, discount_price, format_eur, vat_price
    from schemas import (
        CagrRequest,
        CagrResponse,
        DiscountPriceRequest,
        EurResponse,
        FormatEurRequest,
        PriceResponse,
        VatPriceRequest,
    )

router = APIRouter(prefix="/api/finance", tags=["finance"])


def _bad_request(exc: Exception) -> JSONResponse:
    """Direkten 400 JSONResponse namesto HTTPException."""
    return JSONResponse(status_code=400, content={"error": str(exc)})


@router.post("/vat-price", response_model=PriceResponse)
def vat_price_endpoint(payload: VatPriceRequest) -> JSONResponse:
    try:
        result = vat_price(payload.price, payload.rate)
    except (TypeError, ValueError) as exc:
        return _bad_request(exc)
    return JSONResponse(status_code=200, content={"price": result})


@router.post("/discount", response_model=PriceResponse)
def discount_price_endpoint(payload: DiscountPriceRequest) -> JSONResponse:
    try:
        result = discount_price(payload.price, payload.percent)
    except (TypeError, ValueError) as exc:
        return _bad_request(exc)
    return JSONResponse(status_code=200, content={"price": result})


@router.post("/format-eur", response_model=EurResponse)
def format_eur_endpoint(payload: FormatEurRequest) -> JSONResponse:
    try:
        result = format_eur(payload.value)
    except (TypeError, ValueError) as exc:
        return _bad_request(exc)
    return JSONResponse(status_code=200, content={"value": result})


@router.post("/cagr", response_model=CagrResponse)
def cagr_endpoint(payload: CagrRequest) -> JSONResponse:
    try:
        result = cagr(payload.values)
    except (TypeError, ValueError) as exc:
        return _bad_request(exc)
    return JSONResponse(status_code=200, content={"cagr": result})


app = FastAPI(title="finance_calc API", version="1.0.0")
app.include_router(router)