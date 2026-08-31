"""FastAPI integracijski router za modul fleet_status.

Izpostavi stanje flote na `GET /api/fleet/status`. Napake prevaja v
direktne JSONResponse odzive: 404 za manjkajoče datoteke, 400 za
poškodovane/neveljavne podatke in 500 za nepričakovane napake.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .fleet_status import collect_status

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


@router.get("/status")
async def get_fleet_status(data_dir: Optional[str] = None) -> JSONResponse:
    """Vrni trenutno stanje flote (daemon + workerji) kot JSON."""
    try:
        status = collect_status(data_dir)
    except FileNotFoundError as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=404)
    except ValueError as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=400)
    except Exception:
        return JSONResponse(
            content={"error": "internal server error"}, status_code=500
        )
    return JSONResponse(content=status, status_code=200)