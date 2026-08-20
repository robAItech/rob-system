"""Test za demo_bug — ujame namerno napako (deljenje z nič)."""

import pytest

from actions.demo_bug.demo_bug import divide


def test_divide_normal():
    assert divide(10, 2) == 5.0


def test_divide_by_zero_raises_valueerror():
    """NAMERNA pričakovana napaka: divide(10, 0) bi moral vrniti ValueError."""
    with pytest.raises(ValueError):
        divide(10, 0)
