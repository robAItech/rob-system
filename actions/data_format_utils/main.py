"""data_format_utils — FastAPI aplikacija (API plast, Refaktor 3).

Expose: csv parse, iso parse, deep merge + health. Exporta ``app`` — v
runtime pod ``/api/data_format_utils/*``.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from actions.data_format_utils.formats import deep_merge, parse_csv, parse_iso
from actions.data_format_utils.schemas import (
    CsvParseRequest,
    DeepMergeRequest,
    IsoParseRequest,
)

app = FastAPI(title="Rob AI Studio - Data Format Utils", version="1.0.0")


@app.post("/csv-parse")
async def csv_parse(body: CsvParseRequest) -> JSONResponse:
    """Razčleni CSV v seznam vrstic."""
    return JSONResponse({"rows": parse_csv(body.text, body.delimiter)})


@app.post("/iso-parse")
async def iso_parse(body: IsoParseRequest) -> JSONResponse:
    """Razčleni ISO datum; 400 ob neveljavnem vnosu."""
    try:
        return JSONResponse({"value": parse_iso(body.value).isoformat()})
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.post("/deep-merge")
async def deep_merge_endpoint(body: DeepMergeRequest) -> JSONResponse:
    """Rekurzivno združi dve JSON strukturi."""
    return JSONResponse({"merged": deep_merge(body.a, body.b)})


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return {"status": "UP"}
