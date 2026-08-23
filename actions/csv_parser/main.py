"""FastAPI integracijski router za ``csv_parser`` modul.

Izvaja dva endpointa:

* ``POST /csv/parse`` — razčleni CSV besedilo v seznam vrstic.
* ``POST /csv/to-csv`` — serializira seznam vrstic nazaj v CSV besedilo.

Napake se vračajo neposredno kot ``JSONResponse`` (4xx/5xx), brez metanja
HTTP izjem.
"""

from typing import Union

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from .csv_parser import parse_csv, to_csv
from .schemas import (
    CSVParseRequest,
    CSVParseResponse,
    CSVToCsvRequest,
    CSVToCsvResponse,
)

router = APIRouter(prefix="/csv", tags=["csv_parser"])


@router.post("/parse")
async def parse_csv_route(
    request: CSVParseRequest,
) -> Union[CSVParseResponse, JSONResponse]:
    """Razčleni CSV besedilo v seznam vrstic."""
    try:
        rows = parse_csv(request.text, request.delimiter)
    except (TypeError, ValueError) as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # pragma: no cover - varnostna mreža
        return JSONResponse(
            status_code=500,
            content={"detail": f"Nepričakovana napaka: {exc}"},
        )
    return CSVParseResponse(rows=rows)


@router.post("/to-csv")
async def to_csv_route(
    request: CSVToCsvRequest,
) -> Union[CSVToCsvResponse, JSONResponse]:
    """Serializira seznam vrstic nazaj v CSV besedilo."""
    try:
        text = to_csv(request.rows, request.delimiter)
    except (TypeError, ValueError) as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # pragma: no cover - varnostna mreža
        return JSONResponse(
            status_code=500,
            content={"detail": f"Nepričakovana napaka: {exc}"},
        )
    return CSVToCsvResponse(text=text)


# Priročna FastAPI aplikacija (alternativa: vključi ``router`` v svojo aplikacijo).
app = FastAPI(title="csv_parser API")
app.include_router(router)