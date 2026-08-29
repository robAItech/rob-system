"""Pytest test suite za actions.fleet_sync_check.add2."""

from __future__ import annotations

import pytest

try:
    from actions.fleet_sync_check import add2
except ImportError:  # pragma: no cover - fallback za standalone zagon
    from fleet_sync_check import add2


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (1, 2, 3),
        (0, 0, 0),
        (-5, 5, 0),
        (-3, -7, -10),
        (2.5, 1.5, 4.0),
        (100, 200, 300),
        (0.1, 0.2, 0.3),
    ],
)
def test_add2_known_values(a, b, expected):
    assert add2(a, b) == expected


def test_add2_returns_int_for_ints():
    result = add2(2, 3)
    assert result == 5
    assert isinstance(result, int)


def test_add2_returns_float_for_floats():
    result = add2(1.5, 2.5)
    assert result == 4.0
    assert isinstance(result, float)


def test_add2_commutative():
    assert add2(7, 3) == add2(3, 7)


def test_add2_roundtrip_subtraction():
    total = add2(10, 5)
    assert total - 5 == 10
