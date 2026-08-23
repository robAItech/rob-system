"""FastAPI integracijski router za modul invoice_calc.

Uporablja neposredne JSONResponse odgovore za 4xx/5xx napake:
- 422 → neveljavna vhodna shema (RequestValidationError)
- 400 → logična napaka pri izračunu (InvoiceValidationError)
- 500 → nepričakovana napaka (vedno JSON, ne HTML)

Vsi odgovori uporabljajo `SerializableJSONResponse` (podrazred starlette
`JSONResponse` z metodo `.json()`), da lahko tudi neposredni klici endpoint
funkcije (brez TestClient) preberejo telo kot Python dict. Ker je to še vedno
starlette `Response`, ga FastAPI prepozna in posreduje naprej — TestClient
pot (httpx) deluje nespremenjeno.
"""
from __future__ import annotations

import json as _json

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .invoice_calc import InvoiceValidationError, calculate_invoice
from .schemas import InvoiceRequest, InvoiceResult

router = APIRouter(prefix="/invoice", tags=["invoice"])


class SerializableJSONResponse(JSONResponse):
    """JSONResponse z metodo `.json()` za direktne klice endpoint funkcij."""

    def json(self) -> dict:
        """Vrne telo odgovora, razčlenjeno iz JSON v Python dict."""
        return _json.loads(self.body.decode("utf-8"))


@router.post(
    "/calculate",
    response_model=InvoiceResult,
    summary="Izračun fakture z DDV in popusti",
)
async def calculate_invoice_endpoint(
    payload: InvoiceRequest,
) -> SerializableJSONResponse:
    try:
        result = await calculate_invoice(payload)
    except InvoiceValidationError as exc:
        return SerializableJSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception:  # noqa: BLE001 — 5xx mora biti JSON, ne HTML
        return SerializableJSONResponse(
            status_code=500, content={"detail": "Notranja napaka strežnika."}
        )
    # mode="json": Decimal → str, da je odgovor JSON-serializabilen.
    return SerializableJSONResponse(
        status_code=200, content=result.model_dump(mode="json")
    )


app = FastAPI(title="Invoice Calc API", version="1.0.0")
app.include_router(router)


@app.post(
    "/calculate",
    response_model=InvoiceResult,
    include_in_schema=False,
)
async def calculate_alias(payload: InvoiceRequest) -> SerializableJSONResponse:
    """Sopomenska pot brez /invoice prefiksa (združljivost)."""
    return await calculate_invoice_endpoint(payload)


@app.get("/health", include_in_schema=False)
async def health() -> SerializableJSONResponse:
    return SerializableJSONResponse(status_code=200, content={"status": "ok"})


@app.exception_handler(RequestValidationError)
async def _request_validation_handler(
    request: Request, exc: RequestValidationError
) -> SerializableJSONResponse:
    return SerializableJSONResponse(
        status_code=422,
        content={
            "detail": "Neveljavni podatki zahteve.",
            "errors": [
                {
                    "loc": list(error.get("loc", [])),
                    "msg": error.get("msg", "neveljavna vrednost"),
                    "type": error.get("type", "value_error"),
                }
                for error in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> SerializableJSONResponse:
    return SerializableJSONResponse(
        status_code=500, content={"detail": "Notranja napaka strežnika."}
    )


__all__ = [
    "SerializableJSONResponse",
    "app",
    "router",
    "calculate_invoice_endpoint",
]