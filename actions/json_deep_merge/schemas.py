"""Pydantic V2 schemas for the ``actions.json_deep_merge`` FastAPI router.

The merge utility itself is schema-free; these models only describe the
optional HTTP integration surface (``POST /merge``) and are never required
by plain pytest runs of the module.
"""
from __future__ import annotations

from typing import Any

try:  # pragma: no cover - optional integration surface
    from pydantic import BaseModel

    class MergeRequest(BaseModel):
        """Request payload: the two JSON-like structures to merge."""

        a: Any
        b: Any

    class MergeResponse(BaseModel):
        """Response payload: the merged structure."""

        result: Any

except ImportError:  # pragma: no cover - pydantic not installed
    MergeRequest = None  # type: ignore[assignment,misc]
    MergeResponse = None  # type: ignore[assignment,misc]