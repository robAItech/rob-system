"""FastAPI integration router for the signal_calc module.

Direct JSONResponse handling for 4xx (validation) and 5xx (runtime) errors.
"""

from typing import Dict, Union

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from actions.signal_calc.clamp import clamp
from actions.signal_calc.moving_average import moving_average
from actions.signal_calc.schemas import (
    ClampRequest,
    MovingAverageRequest,
    ZScoreRequest,
)
from actions.signal_calc.z_score import z_score

router = APIRouter(prefix="/signal_calc", tags=["signal_calc"])


def _ok(data: Union[Dict, list, float]) -> JSONResponse:
    return JSONResponse(status_code=200, content={"data": data})


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


@router.post("/moving_average")
async def api_moving_average(req: MovingAverageRequest) -> JSONResponse:
    try:
        return _ok(moving_average(req.values, req.window))
    except ValueError as exc:
        return _error(422, str(exc))
    except Exception as exc:  # pragma: no cover - defensive 5xx
        return _error(500, str(exc))


@router.post("/z_score")
async def api_z_score(req: ZScoreRequest) -> JSONResponse:
    try:
        return _ok(z_score(req.values, req.x))
    except ValueError as exc:
        return _error(422, str(exc))
    except Exception as exc:  # pragma: no cover - defensive 5xx
        return _error(500, str(exc))


@router.post("/clamp")
async def api_clamp(req: ClampRequest) -> JSONResponse:
    try:
        return _ok(clamp(req.value, req.min, req.max))
    except Exception as exc:  # pragma: no cover - defensive 5xx
        return _error(500, str(exc))