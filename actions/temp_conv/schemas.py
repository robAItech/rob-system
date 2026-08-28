"""Pydantic V2 schemas for the temp_conv HTTP API."""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Scale = Literal["celsius", "fahrenheit", "kelvin"]


class ConversionRequest(BaseModel):
    """Request body carrying the temperature value to convert."""

    model_config = ConfigDict(strict=True, extra="forbid")

    value: float = Field(..., description="Temperature value to convert")

    @field_validator("value")
    @classmethod
    def _value_must_be_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("value must be a finite number")
        return v


class ConversionResponse(BaseModel):
    """Successful conversion result."""

    model_config = ConfigDict(strict=True, extra="forbid")

    from_scale: Scale
    to_scale: Scale
    value: float
    result: float