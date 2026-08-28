"""FastAPI integration router za modul sup_kanu.

Arhitekturna usmeritev:
  - API: FastAPI z direct JSONResponse 4xx/5xx handlingom.
  - Stran: GET / vrne celotno HTML stran (index.html).
  - Podatki: GET /api/content vrne strukturirano vsebino (JSON).
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from .sup_kanu import build_site_html, get_site_content

router = APIRouter(tags=["sup_kanu"])


@router.get("/", response_class=HTMLResponse)
async def get_site_page() -> HTMLResponse | JSONResponse:
    """Vrni celotno HTML spletno stran SUP Kanu Ljubljanica."""
    try:
        html = await build_site_html()
    except FileNotFoundError as exc:
        return JSONResponse(status_code=404, content={"error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": f"Napaka pri pripravi strani: {exc}"})
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8")


@router.get("/api/content")
async def get_content_api() -> JSONResponse:
    """Vrni strukturirano vsebino spletne strani v JSON obliki."""
    try:
        content = await get_site_content()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": f"Napaka pri pripravi vsebine: {exc}"})
    return JSONResponse(content=content.model_dump())


@router.get("/api/health")
async def health() -> JSONResponse:
    """Preprosta zdravstvena kontrola modula."""
    return JSONResponse(content={"status": "ok", "module": "sup_kanu"})
