"""Pydantic V2 request schemas for the signal_calc API (strict validators)."""

from typing import List

from pydantic import BaseModel, Field, field_validator


class MovingAverageRequest(BaseModel):
    """Request: moving average over a sequence."""

    values: List[float] = Field(..., min_length=1)
    window: int = Field(..., gt=0, strict=True)

    @field_validator("window")
    @classmethod
    def window_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("window must be > 0")
        return v


class ZScoreRequest(BaseModel):
    """Request: z-score of x within a population."""

    values: List[float] = Field(..., min_length=1)
    x: float


class ClampRequest(BaseModel):
    """Request: clamp a value into the [min, max] interval."""

    value: float
    min: float
    max: float