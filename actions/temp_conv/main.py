"""FastAPI integration router for the temp_conv module.

Exposes the temperature conversion functions over HTTP with direct
JSONResponse-based 4xx/5xx error handling (no HTTPException raises).
"""
from __future__ import annotations

from typing import Callable, Dict, Tuple

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .schemas import ConversionRequest, ConversionResponse
from .temp_conv import c_to_f, c_to_k, f_to_c

router = APIRouter(prefix="/temp-conv", tags=["temp_conv"])

Converter = Callable[[float], float]

_CONVERTERS: Dict[str, Tuple[str, str, Converter]] = {
    "c-to-f": ("celsius", "fahrenheit", c_to_f),
    "f-to-c": ("fahrenheit", "celsius", f_to_c),
    "c-to-k": ("celsius", "kelvin", c_to_k),
}


@router.get("/health")
async def health() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse(status_code=200, content={"status": "ok"})


@router.post("/convert/{conversion}")
async def convert(conversion: str, request: ConversionRequest) -> JSONResponse:
    """Convert a temperature value between two scales."""
    entry = _CONVERTERS.get(conversion)
    if entry is None:
        return JSONResponse(
            status_code=400,
            content={"error": f"unknown conversion: '{conversion}'"},
        )
    from_scale, to_scale, fn = entry
    try:
        result = fn(request.value)
    except (TypeError, ValueError) as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception:
        return JSONResponse(status_code=500, content={"error": "internal server error"})
    return JSONResponse(
        status_code=200,
        content=ConversionResponse(
            from_scale=from_scale,
            to_scale=to_scale,
            value=float(request.value),
            result=float(result),
        ).model_dump(),
    )