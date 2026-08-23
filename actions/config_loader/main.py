"""main.py — FastAPI Integration Router za actions.config_loader."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .config_loader import parse_env, parse_ini
from .schemas import ParseEnvRequest, ParseIniRequest

router = APIRouter(prefix="/config-loader", tags=["config-loader"])


@router.get("/health")
async def health() -> JSONResponse:
    """Preprost health-check."""
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.post("/parse-env")
async def api_parse_env(request: ParseEnvRequest) -> JSONResponse:
    """Razčleni .env vsebino in vrne slovar.

    4xx/5xx se vrača neposredno kot ``JSONResponse``.
    """
    try:
        data = parse_env(request.text)
    except TypeError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # pragma: no cover — defenzivno
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(status_code=200, content={"data": data})


@router.post("/parse-ini")
async def api_parse_ini(request: ParseIniRequest) -> JSONResponse:
    """Razčleni INI vsebino in vrne slovar sekcij.

    4xx/5xx se vrača neposredno kot ``JSONResponse``.
    """
    try:
        data = parse_ini(request.text)
    except TypeError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except Exception as exc:  # pragma: no cover — defenzivno
        return JSONResponse(status_code=500, content={"detail": str(exc)})
    return JSONResponse(status_code=200, content={"data": data})