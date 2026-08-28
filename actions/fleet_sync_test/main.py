"""FastAPI integration router exposing ``mul`` over HTTP.

Error handling uses explicit ``JSONResponse`` objects for the 4xx/5xx cases
(400 for client-side value errors, 500 as a defensive guard) and a direct
``JSONResponse`` for the successful 200 case.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .fleet_sync_test import mul
from .schemas import MulRequest

router = APIRouter(prefix="/fleet-sync-test", tags=["fleet_sync_test"])


@router.post("/mul")
async def multiply(payload: MulRequest) -> JSONResponse:
    """Multiply ``payload.a * payload.b`` and return a JSON response."""
    try:
        result = mul(payload.a, payload.b)
    except (TypeError, ValueError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception:
        return JSONResponse(
            status_code=500, content={"error": "internal server error"}
        )
    return JSONResponse(status_code=200, content={"result": result})


__all__ = ["multiply", "router"]
