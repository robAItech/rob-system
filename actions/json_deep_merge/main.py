"""FastAPI integration router for ``actions.json_deep_merge``.

Exposes ``POST /merge``: accepts two JSON-like payloads, deep-merges them
with :func:`deep_merge` and answers with a direct ``JSONResponse``
(explicit 4xx/5xx handling).  The router is optional integration surface;
plain pytest runs of the module never require FastAPI.
"""
from __future__ import annotations

from typing import Any

from .json_deep_merge import deep_merge

try:  # pragma: no cover - optional integration surface
    from fastapi import APIRouter, HTTPException
    from fastapi.responses import JSONResponse

    from .schemas import MergeRequest

    router = APIRouter()

    @router.post("/merge", response_class=JSONResponse)
    def merge(payload: MergeRequest) -> JSONResponse:
        """Deep-merge ``payload.b`` into ``payload.a``."""
        try:
            merged: Any = deep_merge(payload.a, payload.b)
        except Exception as exc:  # pragma: no cover - defensive 5xx
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return JSONResponse(status_code=200, content=merged)
except ImportError:  # pragma: no cover - FastAPI not installed
    router = None  # type: ignore[assignment]