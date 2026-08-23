"""ini_config — FastAPI integration router.

Exposes the parsing/reading logic over HTTP with explicit ``JSONResponse``
4xx/5xx handling (no default HTML error pages).
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .ini_config import parse_ini, read_ini
from .schemas import ParseRequest

__all__ = ["router"]

router = APIRouter(prefix="/ini-config", tags=["ini-config"])


@router.get("/health")
async def health() -> JSONResponse:
    """Liveness probe."""
    return JSONResponse({"status": "ok"})


@router.post("/parse")
async def parse_endpoint(payload: ParseRequest) -> JSONResponse:
    """Parse raw INI text and return ``{section: {key: value}}``.

    ``400`` is returned with a JSON body when the input cannot be parsed.
    """
    try:
        result = parse_ini(payload.text)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return JSONResponse(status_code=400, content={"error": str(exc)})
    return JSONResponse(result)


@router.get("/read")
async def read_endpoint(
    path: str = Query(..., description="Filesystem path of the INI file to read."),
) -> JSONResponse:
    """Read and parse an INI file from disk.

    * ``404`` when the file does not exist,
    * ``400`` for other read/parse failures,
    * ``200`` with the parsed document otherwise.
    """
    try:
        result = read_ini(path)
    except FileNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": f"file not found: {path}"},
        )
    except OSError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return JSONResponse(result)