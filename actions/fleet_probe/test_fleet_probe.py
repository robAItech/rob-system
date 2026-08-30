"""Pytest test suite za actions.fleet_probe.add.

Pokriva znane vrednosti, robne pogoje (negativi, ničla, float, velika
števila) in roundtrip preverjanje.
"""

import sys
from pathlib import Path

import pytest

try:
    from actions.fleet_probe.fleet_probe import add
except ModuleNotFoundError:  # pragma: no cover — fallback za ne-package okolja
    sys.path.insert(
        0, str(Path(__file__).resolve().parents[1] / "actions" / "fleet_probe")
    )
    from fleet_probe import add


def test_add_known_values():
    assert add(1, 2) == 3
    assert add(0, 0) == 0
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-1, 1) == 0
    assert add(-5, -3) == -8


def test_add_float():
    assert add(1.5, 2.25) == 3.75
    assert add(0.1, 0.2) == pytest.approx(0.3)


def test_add_large():
    assert add(10**12, 10**12) == 2 * 10**12
    assert add(10**18, 1) == 10**18 + 1


def test_add_commutative():
    assert add(7, 3) == add(3, 7)
    assert add(-4, 9) == add(9, -4)


def test_add_roundtrip():
    # roundtrip: (a + b) - b == a
    assert add(add(10, 5), -5) == 10
    assert add(add(3.5, 1.25), -1.25) == pytest.approx(3.5)


def test_package_reexport():
    pkg_add = pytest.importorskip("actions.fleet_probe").add
    assert pkg_add(2, 3) == 5