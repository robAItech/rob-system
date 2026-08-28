"""Pytest test suite za finance_calc (`naredi`) modul.

Pokriva vse štiri čiste funkcije skupaj z robnimi primeri:
* ``vat_price``      — cena z DDV, zaokrožena na 2 decimalki;
* ``discount_price`` — cena s popustom; percent 0–100, sicer ValueError;
* ``format_eur``     — EUR niz po slovenski konvenciji;
* ``cagr``           — CAGR v %, zaokrožen na 2 decimalki.
"""

from __future__ import annotations

import math

import pytest

try:
    from naredi import cagr, discount_price, format_eur, vat_price
except ImportError:  # pragma: no cover — fallback za paketni uvoz
    from actions.naredi import cagr, discount_price, format_eur, vat_price


# ---------------------------------------------------------------------------
# vat_price
# ---------------------------------------------------------------------------

class TestVatPrice:
    def test_standard_rate(self) -> None:
        assert vat_price(100, 0.22) == 122.0

    def test_default_rate_is_22_percent(self) -> None:
        assert vat_price(100) == 122.0

    def test_zero_rate(self) -> None:
        assert vat_price(100, 0.0) == 100.0

    def test_zero_price(self) -> None:
        assert vat_price(0, 0.22) == 0.0

    def test_low_rate(self) -> None:
        assert vat_price(10, 0.05) == 10.5

    def test_rounding_to_two_decimals(self) -> None:
        # 19.99 * 1.22 = 24.3878 -> 24.39
        assert vat_price(19.99, 0.22) == 24.39

    def test_rounding_up_small_value(self) -> None:
        # 0.1 * 1.22 = 0.122 -> 0.12
        assert vat_price(0.1, 0.22) == 0.12

    def test_negative_price(self) -> None:
        assert vat_price(-100, 0.22) == -122.0

    def test_int_input(self) -> None:
        assert vat_price(50, 0.1) == 55.0

    def test_returns_float(self) -> None:
        result = vat_price(100, 0.22)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# discount_price
# ---------------------------------------------------------------------------

class TestDiscountPrice:
    def test_basic_discount(self) -> None:
        assert discount_price(100, 10) == 90.0

    def test_zero_percent(self) -> None:
        assert discount_price(100, 0) == 100.0

    def test_full_discount(self) -> None:
        assert discount_price(100, 100) == 0.0

    def test_quarter_discount(self) -> None:
        assert discount_price(50, 25) == 37.5

    def test_rounding_to_two_decimals(self) -> None:
        # 19.99 * 0.9 = 17.991 -> 17.99
        assert discount_price(19.99, 10) == 17.99

    def test_non_round_percent(self) -> None:
        # 10 * (1 - 33/100) = 6.7
        assert discount_price(10, 33) == 6.7

    def test_int_price(self) -> None:
        assert discount_price(200, 20) == 160.0

    def test_negative_price(self) -> None:
        assert discount_price(-100, 10) == -90.0

    def test_percent_below_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            discount_price(100, -1)

    def test_percent_above_hundred_raises(self) -> None:
        with pytest.raises(ValueError):
            discount_price(100, 101)

    def test_boundary_zero_accepted(self) -> None:
        assert discount_price(50, 0.0) == 50.0

    def test_boundary_hundred_accepted(self) -> None:
        assert discount_price(50, 100.0) == 0.0

    def test_returns_float(self) -> None:
        result = discount_price(100, 10)
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# format_eur
# ---------------------------------------------------------------------------

class TestFormatEur:
    def test_whole_number_no_decimals(self) -> None:
        assert format_eur(5) == "5 EUR"

    def test_two_decimals_with_comma(self) -> None:
        assert format_eur(5.5) == "5,50 EUR"

    def test_thousands_separated_with_dot(self) -> None:
        assert format_eur(1234567.89) == "1.234.567,89 EUR"

    def test_negative_with_minus(self) -> None:
        assert format_eur(-5.5) == "-5,50 EUR"

    def test_negative_whole(self) -> None:
        assert format_eur(-5) == "-5 EUR"

    def test_zero(self) -> None:
        assert format_eur(0) == "0 EUR"

    def test_zero_float(self) -> None:
        assert format_eur(0.0) == "0 EUR"

    def test_negative_zero(self) -> None:
        assert format_eur(-0.0) == "0 EUR"

    def test_thousand_whole(self) -> None:
        assert format_eur(1000) == "1.000 EUR"

    def test_million_whole(self) -> None:
        assert format_eur(1000000.0) == "1.000.000 EUR"

    def test_single_decimal(self) -> None:
        assert format_eur(0.1) == "0,10 EUR"

    def test_rounding(self) -> None:
        assert format_eur(123.456) == "123,46 EUR"

    def test_negative_large(self) -> None:
        assert format_eur(-1234567.89) == "-1.234.567,89 EUR"

    def test_string_number_accepted(self) -> None:
        assert format_eur("5.5") == "5,50 EUR"

    def test_nan_raises(self) -> None:
        with pytest.raises(ValueError):
            format_eur(float("nan"))

    def test_inf_raises(self) -> None:
        with pytest.raises(ValueError):
            format_eur(float("inf"))

    def test_negative_inf_raises(self) -> None:
        with pytest.raises(ValueError):
            format_eur(float("-inf"))

    def test_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError):
            format_eur("abc")

    def test_returns_str(self) -> None:
        result = format_eur(5.5)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# cagr
# ---------------------------------------------------------------------------

class TestCagr:
    def test_empty_list_returns_zero(self) -> None:
        assert cagr([]) == 0.0

    def test_single_value_returns_zero(self) -> None:
        assert cagr([100]) == 0.0

    def test_growth_between_two_years(self) -> None:
        # (121 / 100) ** 1 - 1 = 0.21 -> 21.0 %
        assert cagr([100, 121]) == 21.0

    def test_growth_over_three_years(self) -> None:
        # (121 / 100) ** 0.5 - 1 = 0.1 -> 10.0 %
        assert cagr([100, 110, 121]) == 10.0

    def test_decline(self) -> None:
        assert cagr([100, 50]) == -50.0

    def test_decline_over_three_years(self) -> None:
        # (64 / 100) ** 0.5 - 1 = -0.2 -> -20.0 %
        assert cagr([100, 80, 64]) == -20.0

    def test_zero_first_value_returns_zero(self) -> None:
        assert cagr([0, 100]) == 0.0

    def test_zero_last_value_returns_zero(self) -> None:
        assert cagr([100, 0]) == 0.0

    def test_negative_values_return_zero(self) -> None:
        assert cagr([-100, 100]) == 0.0

    def test_doubling(self) -> None:
        assert cagr([100, 200]) == 100.0

    def test_no_change(self) -> None:
        assert cagr([100, 100]) == 0.0

    def test_rounding_to_two_decimals(self) -> None:
        # (150 / 100) - 1 = 0.5 -> 50.0 %
        assert cagr([100, 150]) == 50.0

    def test_returns_float(self) -> None:
        result = cagr([100, 121])
        assert isinstance(result, float)
