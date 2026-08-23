"""FastAPI integration router for config_manager.

Exposes the merged configuration over HTTP with direct JSONResponse
handling for 4xx (missing key -> 404) responses.
"""

from __future__ import annotations

from typing import Dict

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .config_manager import ConfigManager

router = APIRouter(prefix="/config", tags=["config"])

_manager = ConfigManager()


def set_manager(manager: ConfigManager) -> None:
    """Replace the router's backing manager (mainly for tests)."""
    global _manager
    _manager = manager


@router.get("", response_model=Dict[str, str])
async def get_all() -> Dict[str, str]:
    """Return the full merged configuration."""
    return _manager.all()


@router.get("/{key}")
async def get_key(key: str) -> JSONResponse:
    """Return a single config value; 404 JSONResponse when the key is missing."""
    value = _manager.get(key)
    if value is None:
        return JSONResponse(
            status_code=404,
            content={"error": "key_not_found", "key": key},
        )
    return JSONResponse(
        status_code=200,
        content={"key": key, "value": value},
    )