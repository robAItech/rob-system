"""Clamp: restrict a value to the closed interval [min, max]."""

from typing import Union


def clamp(v: Union[int, float], min: Union[int, float], max: Union[int, float]) -> float:
    """Return `v` clamped into [min, max] (a < b, otherwise b < a → a)."""
    if v < min:
        return min
    if v > max:
        return max
    return v