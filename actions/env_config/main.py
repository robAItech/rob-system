"""FastAPI Integration Router za env_config.

Izpostavlja tri končne točke:
  * ``POST /parse``  — razčleni .env vsebino (telo: ``{"text": "..."}``);
  * ``POST /load``   — prebere .env datoteko s poti (telo: ``{"path": "..."}``);
  * ``GET  /health`` — preprost health-check.

Napake se vračajo kot direktni ``JSONResponse`` s 4xx/5xx statusi
(404 za manjkajočo datoteko, 400 za neveljavno pot, 500 za nepričakovano napako).
"""

from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from env_config import load_env, parse_env
    from schemas import EnvLoadRequest, EnvParseRequest, EnvParseResponse
except ImportError:  # pragma: no cover — odvisno od načina uvoza (paket vs. top-level)
    from .env_config import load_env, parse_env
    from .schemas import EnvLoadRequest, EnvParseRequest, EnvParseResponse

router = APIRouter(tags=["env_config"])


@router.post("/parse")
def api_parse(request: EnvParseRequest) -> JSONResponse:
    """Razčleni .env vsebino in vrne slovar + število vnosov."""
    try:
        data: Dict[str, str] = parse_env(request.text)
        payload = EnvParseResponse(data=data, count=len(data)).model_dump()
        return JSONResponse(content=payload, status_code=200)
    except Exception as exc:  # pragma: no cover — varnostna mreža
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.post("/load")
def api_load(request: EnvLoadRequest) -> JSONResponse:
    """Prebere .env datoteko s poti in vrne slovar + število vnosov."""
    try:
        data: Dict[str, str] = load_env(request.path)
        payload = EnvParseResponse(data=data, count=len(data)).model_dump()
        return JSONResponse(content=payload, status_code=200)
    except FileNotFoundError:
        return JSONResponse(content={"error": "datoteka ne obstaja"}, status_code=404)
    except OSError as exc:
        return JSONResponse(content={"error": str(exc)}, status_code=400)
    except Exception as exc:  # pragma: no cover — varnostna mreža
        return JSONResponse(content={"error": str(exc)}, status_code=500)


@router.get("/health")
def api_health() -> JSONResponse:
    """Preprost health-check."""
    return JSONResponse(content={"status": "ok"}, status_code=200)