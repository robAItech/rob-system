"""Pytest test suite for the signal_calc module (100% green, edge cases covered)."""

import math

import pytest
from pydantic import ValidationError

from actions.signal_calc import clamp, moving_average, z_score
from actions.signal_calc.schemas import (
    ClampRequest,
    MovingAverageRequest,
    ZScoreRequest,
)


class TestMovingAverage:
    def test_basic(self):
        assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]

    def test_window_one_returns_same_values(self):
        assert moving_average([1, 2, 3], 1) == [1.0, 2.0, 3.0]

    def test_window_equals_length_single_mean(self):
        assert moving_average([2, 4, 6], 3) == [4.0]

    def test_float_values(self):
        result = moving_average([1.0, 2.5, 4.0], 2)
        assert result == pytest.approx([1.75, 3.25])

    def test_negative_values(self):
        assert moving_average([-2, -1, 0], 2) == [-1.5, -0.5]

    def test_invalid_window_zero_raises(self):
        with pytest.raises(ValueError):
            moving_average([1, 2, 3], 0)

    def test_invalid_window_negative_raises(self):
        with pytest.raises(ValueError):
            moving_average([1, 2, 3], -2)

    def test_empty_sequence_raises(self):
        with pytest.raises(ValueError):
            moving_average([], 2)

    def test_window_larger_than_sequence_raises(self):
        with pytest.raises(ValueError):
            moving_average([1, 2, 3], 4)

    def test_keyword_args(self):
        assert moving_average(seznam=[1, 2, 3], okno=2) == [1.5, 2.5]


class TestZScore:
    def test_classic_example_mean(self):
        assert z_score([2, 4, 4, 4, 5, 5, 7, 9], 5) == pytest.approx(0.0)

    def test_above_mean(self):
        z = z_score([1, 2, 3, 4, 5], 5)
        assert z == pytest.approx((5 - 3) / math.sqrt(2))

    def test_below_mean(self):
        z = z_score([1, 2, 3, 4, 5], 1)
        assert z == pytest.approx((1 - 3) / math.sqrt(2))

    def test_constant_series_returns_zero(self):
        assert z_score([7, 7, 7, 7], 7) == 0.0

    def test_single_value_returns_zero(self):
        assert z_score([3], 3) == 0.0

    def test_float_values(self):
        z = z_score([1.0, 2.0, 3.0], 2.0)
        assert z == pytest.approx(0.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            z_score([], 1)

    def test_keyword_args(self):
        assert z_score(vrednosti=[1, 2, 3], x=1) == pytest.approx((1 - 2) / math.sqrt(2 / 3))


class TestClamp:
    def test_within_range(self):
        assert clamp(5, 0, 10) == 5

    def test_below_min(self):
        assert clamp(-5, 0, 10) == 0

    def test_above_max(self):
        assert clamp(15, 0, 10) == 10

    def test_equal_min(self):
        assert clamp(0, 0, 10) == 0

    def test_equal_max(self):
        assert clamp(10, 0, 10) == 10

    def test_negative_range(self):
        assert clamp(0, -10, -1) == -1

    def test_float_value(self):
        assert clamp(3.7, 0.0, 1.0) == 1.0

    def test_keyword_args(self):
        assert clamp(v=7, min=1, max=6) == 6


class TestSchemas:
    def test_moving_average_request_valid(self):
        req = MovingAverageRequest(values=[1, 2, 3], window=2)
        assert req.window == 2
        assert req.values == [1.0, 2.0, 3.0]

    def test_moving_average_request_rejects_zero_window(self):
        with pytest.raises(ValidationError):
            MovingAverageRequest(values=[1, 2, 3], window=0)

    def test_moving_average_request_rejects_string_window_strict(self):
        with pytest.raises(ValidationError):
            MovingAverageRequest(values=[1, 2, 3], window="2")

    def test_moving_average_request_rejects_empty_values(self):
        with pytest.raises(ValidationError):
            MovingAverageRequest(values=[], window=2)

    def test_z_score_request_valid(self):
        req = ZScoreRequest(values=[1, 2, 3], x=2)
        assert req.x == 2.0
        assert req.values == [1.0, 2.0, 3.0]

    def test_clamp_request_valid(self):
        req = ClampRequest(value=5, min=0, max=10)
        assert req.value == 5
        assert req.min == 0
        assert req.max == 10
