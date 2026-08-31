"""FastAPI integracijski router za health_metrics.

Izpostavi ``GET /health/metrics`` in ``GET /health/summary``.
Vse napake se vračajo kot eksplicitni ``JSONResponse`` s statusi 4xx/5xx —
nikoli kot neulovljene izjeme.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .health_metrics import collect_metrics, summary

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/metrics", response_class=JSONResponse)
def get_metrics(base_dir: Optional[str] = None) -> JSONResponse:
    """Vrni zbrane metrike stanja sistema kot JSON.

    Args:
        base_dir: Opcijski korenski imenik za ``.rob_ai/`` (testiranje).

    Returns:
        200 z dict metrik ali 500 ob nepričakovani napaki.
    """
    try:
        data: Dict[str, Any] = collect_metrics(base_dir)
    except Exception as exc:  # pragma: no cover — defensivno
        return JSONResponse(
            status_code=500,
            content={"error": f"failed to collect metrics: {exc}"},
        )
    return JSONResponse(content=data)


@router.get("/summary", response_class=JSONResponse)
def get_summary(base_dir: Optional[str] = None) -> JSONResponse:
    """Vrni kratek tekstovni povzetek stanja sistema.

    Args:
        base_dir: Opcijski korenski imenik za ``.rob_ai/`` (testiranje).

    Returns:
        200 z ``{"summary": "..."}`` ali 500 ob nepričakovani napaki.
    """
    try:
        text: str = summary(base_dir)
    except Exception as exc:  # pragma: no cover — defensivno
        return JSONResponse(
            status_code=500,
            content={"error": f"failed to build summary: {exc}"},
        )
    return JSONResponse(content={"summary": text})