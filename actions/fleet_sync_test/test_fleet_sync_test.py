"""Pytest suite for the fleet_sync_test module.

Covers the core ``mul`` / ``amul`` logic (including edge cases: negatives,
zero, floats, large integers, commutativity), the strict Pydantic V2 schema
validation and the FastAPI router's direct JSONResponse 4xx/5xx handling.
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

try:
    from fleet_sync_test import MulRequest, MulResponse, amul, mul
    from fleet_sync_test import main as main_module
except ImportError:  # pragma: no cover - alternate repo-root layout
    from actions.fleet_sync_test import MulRequest, MulResponse, amul, mul
    from actions.fleet_sync_test import main as main_module


# --- mul: core semantics ---------------------------------------------------


def test_mul_positive_ints() -> None:
    assert mul(3, 4) == 12


def test_mul_negative_ints() -> None:
    assert mul(-2, 5) == -10
    assert mul(-3, -4) == 12


def test_mul_zero() -> None:
    assert mul(0, 7) == 0
    assert mul(7, 0) == 0


def test_mul_floats() -> None:
    assert mul(2.5, 2.0) == 5.0
    assert mul(0.1, 0.2) == pytest.approx(0.02)


def test_mul_mixed_numeric_types() -> None:
    assert mul(3, 2.5) == 7.5
    assert mul(1.5, 4) == 6.0


def test_mul_large_ints() -> None:
    assert mul(10**18, 10**18) == 10**36


def test_mul_commutative() -> None:
    for a, b in [(2, 9), (-3, 7), (0.5, 8), (11, -4)]:
        assert mul(a, b) == mul(b, a)


# --- amul: async wrapper ---------------------------------------------------


async def test_amul_returns_product() -> None:
    assert await amul(6, 7) == 42


async def test_amul_matches_mul() -> None:
    for a, b in [(2, 3), (-1, 8), (2.5, 4)]:
        assert await amul(a, b) == mul(a, b)


# --- schemas: strict Pydantic V2 validation --------------------------------


def test_mul_request_accepts_numbers() -> None:
    req = MulRequest(a=3, b=4.5)
    assert req.a == 3
    assert req.b == 4.5


def test_mul_request_rejects_strings() -> None:
    with pytest.raises(ValidationError):
        MulRequest(a="3", b=4)


def test_mul_request_rejects_booleans() -> None:
    with pytest.raises(ValidationError):
        MulRequest(a=True, b=4)


def test_mul_response_accepts_result() -> None:
    resp = MulResponse(result=12)
    assert resp.result == 12


# --- router: direct JSONResponse 4xx/5xx handling --------------------------


async def test_mul_endpoint_success() -> None:
    response = await main_module.multiply(MulRequest(a=6, b=7))
    assert response.status_code == 200
    assert json.loads(response.body) == {"result": 42}


async def test_mul_endpoint_400_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(a, b):  # noqa: ARG001
        raise ValueError("boom")

    monkeypatch.setattr(main_module, "mul", _boom)
    response = await main_module.multiply(MulRequest(a=1, b=2))
    assert response.status_code == 400
    assert json.loads(response.body) == {"error": "boom"}


async def test_mul_endpoint_500_on_unexpected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _kaboom(a, b):  # noqa: ARG001
        raise RuntimeError("kaboom")

    monkeypatch.setattr(main_module, "mul", _kaboom)
    response = await main_module.multiply(MulRequest(a=1, b=2))
    assert response.status_code == 500
    assert json.loads(response.body) == {"error": "internal server error"}
