"""Pydantic V2 schemas for the fleet_sync_test API.

Both models use strict mode so that no implicit coercion happens at the API
boundary, and a dedicated validator rejects booleans (which are ``int``
subclasses in Python but must not be accepted as numbers here).
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, field_validator

Numeric = Union[int, float]


class MulRequest(BaseModel):
    """Strict request payload for the multiplication endpoint."""

    model_config = ConfigDict(strict=True)

    a: Numeric
    b: Numeric

    @field_validator("a", "b")
    @classmethod
    def reject_booleans(cls, value: Numeric) -> Numeric:
        if isinstance(value, bool):
            raise ValueError("boolean values are not accepted as numbers")
        return value


class MulResponse(BaseModel):
    """Strict response payload carrying the multiplication result."""

    model_config = ConfigDict(strict=True)

    result: Numeric


__all__ = ["MulRequest", "MulResponse", "Numeric"]
