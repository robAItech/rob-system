"""FastAPI Integration Router — direct JSONResponse 4xx/5xx handling."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

try:
    from .schemas import SlugifyRequest, SlugifyResponse
    from .slugify import slug
except ImportError:  # pragma: no cover - top-level import fallback
    from schemas import SlugifyRequest, SlugifyResponse
    from slugify import slug

router = APIRouter(prefix="/slugify", tags=["slugify"])


@router.post("", response_model=SlugifyResponse)
async def slugify_endpoint(payload: SlugifyRequest) -> SlugifyResponse:
    """POST /slugify — convert a string into a URL slug."""
    try:
        return SlugifyResponse(slug=slug(payload.text))
    except Exception:  # pragma: no cover - defensive 5xx path
        return JSONResponse(status_code=500, content={"detail": "internal server error"})


@router.get("", response_model=SlugifyResponse)
async def slugify_query(
    text: str = Query(..., description="Text to convert into a URL slug"),
) -> SlugifyResponse:
    """GET /slugify?text=... — query-string flavour of the endpoint."""
    try:
        return SlugifyResponse(slug=slug(text))
    except Exception:  # pragma: no cover - defensive 5xx path
        return JSONResponse(status_code=500, content={"detail": "internal server error"})


app = FastAPI(title="slugify", version="1.0.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Direct JSONResponse for 4xx validation failures (no default wrapper)."""
    return JSONResponse(
        status_code=422,
        content={"detail": "validation error", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Direct JSONResponse for 5xx unhandled errors."""
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


@app.post("/", response_model=SlugifyResponse, include_in_schema=False)
async def root_slugify(payload: SlugifyRequest) -> SlugifyResponse:
    """Root alias for POST /slugify."""
    try:
        return SlugifyResponse(slug=slug(payload.text))
    except Exception:  # pragma: no cover - defensive 5xx path
        return JSONResponse(status_code=500, content={"detail": "internal server error"})


app.include_router(router)


__all__ = ["app", "router"]