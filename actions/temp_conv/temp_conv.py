"""Core temperature conversion logic for the temp_conv module.

Pure, deterministic, side-effect free conversion functions:

    c_to_f(c)  -- Celsius -> Fahrenheit
    f_to_c(f)  -- Fahrenheit -> Celsius
    c_to_k(c)  -- Celsius -> Kelvin

Input validation (applied by every function):
    * non-numeric values (str, None, lists, dicts, ...) raise ValueError
    * booleans are rejected (bool is a subclass of int)
    * non-finite values (NaN, +/-inf) raise ValueError

All functions return a float.
"""
from __future__ import annotations

import math
from typing import Union

Number = Union[int, float]


def _as_finite_number(value: Number, name: str) -> float:
    """Coerce ``value`` to float and reject any non-finite / non-numeric input."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def c_to_f(c: Number) -> float:
    """Convert a Celsius temperature to Fahrenheit (F = C * 9/5 + 32)."""
    celsius = _as_finite_number(c, "c")
    return celsius * 9.0 / 5.0 + 32.0


def f_to_c(f: Number) -> float:
    """Convert a Fahrenheit temperature to Celsius (C = (F - 32) * 5/9)."""
    fahrenheit = _as_finite_number(f, "f")
    return (fahrenheit - 32.0) * 5.0 / 9.0


def c_to_k(c: Number) -> float:
    """Convert a Celsius temperature to Kelvin (K = C + 273.15)."""
    celsius = _as_finite_number(c, "c")
    return celsius + 273.15