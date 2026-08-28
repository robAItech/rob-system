"""main.py — FastAPI integracijski router z direktnim JSONResponse 4xx/5xx handlingom.

Vsi odzivi (tudi napake) so JSON: 422 za neveljaven vhod / neuspelo integracijo,
404/405 za neznane poti in 500 za nepričakovane izjeme — nikoli HTML stacktrace.
"""

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

try:  # paketni uvoz (pytest z basedir nad actions/)
    from .schemas import IntegrationRequest
    from .zgradi__s7 import IntegrationEngine
except ImportError:  # pragma: no cover — neposredni uvoz modula
    from schemas import IntegrationRequest  # type: ignore
    from zgradi__s7 import IntegrationEngine  # type: ignore

app = FastAPI(
    title="zgradi__s7 Integration API",
    version="1.0.0",
    description="Povezan sistem: Pydantic V2 sheme + čista async logika + API.",
)

engine = IntegrationEngine()


@app.exception_handler(RequestValidationError)
async def _validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 — neveljaven vhod: vedno JSONResponse, nikoli HTML."""
    return JSONResponse(
        status_code=422,
        content={
            "ok": False,
            "error": "validation_error",
            "details": jsonable_encoder(exc.errors()),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def _http_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """4xx — vse HTTP izjeme (404, 405, ...) pretvorimo v enoten JSONResponse."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "error": "http_error", "detail": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """500 — nepričakovane napake nikoli ne uidejo kot stacktrace."""
    return JSONResponse(
        status_code=500,
        content={"ok": False, "error": "internal_error", "detail": str(exc)},
    )


@app.get("/api/v1/health")
async def health() -> JSONResponse:
    """Health-check: 200 + JSON, če je pogon pripravljen."""
    payload = await engine.health()
    return JSONResponse(status_code=200, content=payload)


@app.post("/api/v1/integrate")
async def integrate(payload: IntegrationRequest) -> JSONResponse:
    """Integracija modulov v povezan sistem.

    - 200: integracija uspešna (vsi moduli prisotni, noben FAILED, vse faze)
    - 422: integracija neuspešna (manjkajoči moduli / nepopolne faze / FAILED)
    """
    result = await engine.integrate(payload)
    status_code = 200 if result.ok else 422
    return JSONResponse(status_code=status_code, content=result.model_dump())


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
