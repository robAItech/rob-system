"""Pytest test suite for the temp_conv module (unit + API)."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from actions.temp_conv import c_to_f, c_to_k, f_to_c
from actions.temp_conv.main import _CONVERTERS, router
from actions.temp_conv.schemas import ConversionRequest, ConversionResponse


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Unit tests: c_to_f
# ---------------------------------------------------------------------------
class TestCToF:
    def test_freezing_point(self):
        assert c_to_f(0) == pytest.approx(32.0)

    def test_boiling_point(self):
        assert c_to_f(100) == pytest.approx(212.0)

    def test_negative_equals_negative_forty(self):
        assert c_to_f(-40) == pytest.approx(-40.0)

    def test_room_temperature(self):
        assert c_to_f(20) == pytest.approx(68.0)

    def test_returns_float(self):
        assert isinstance(c_to_f(0), float)

    def test_invalid_types_raise_value_error(self):
        for bad in ["abc", None, [1, 2], {"x": 1}]:
            with pytest.raises(ValueError):
                c_to_f(bad)

    def test_bool_rejected(self):
        with pytest.raises(ValueError):
            c_to_f(True)

    def test_non_finite_rejected(self):
        for bad in [float("nan"), float("inf"), float("-inf")]:
            with pytest.raises(ValueError):
                c_to_f(bad)


# ---------------------------------------------------------------------------
# Unit tests: f_to_c
# ---------------------------------------------------------------------------
class TestFToC:
    def test_freezing_point(self):
        assert f_to_c(32) == pytest.approx(0.0)

    def test_boiling_point(self):
        assert f_to_c(212) == pytest.approx(100.0)

    def test_negative_equals_negative_forty(self):
        assert f_to_c(-40) == pytest.approx(-40.0)

    def test_body_temperature(self):
        assert f_to_c(98.6) == pytest.approx(37.0, abs=1e-9)

    def test_returns_float(self):
        assert isinstance(f_to_c(32), float)

    def test_invalid_types_raise_value_error(self):
        for bad in ["abc", None, [1, 2], {"x": 1}]:
            with pytest.raises(ValueError):
                f_to_c(bad)

    def test_bool_rejected(self):
        with pytest.raises(ValueError):
            f_to_c(True)

    def test_non_finite_rejected(self):
        for bad in [float("nan"), float("inf"), float("-inf")]:
            with pytest.raises(ValueError):
                f_to_c(bad)


# ---------------------------------------------------------------------------
# Unit tests: c_to_k
# ---------------------------------------------------------------------------
class TestCToK:
    def test_absolute_zero(self):
        assert c_to_k(-273.15) == pytest.approx(0.0, abs=1e-9)

    def test_freezing_point(self):
        assert c_to_k(0) == pytest.approx(273.15)

    def test_room_temperature(self):
        assert c_to_k(20) == pytest.approx(293.15)

    def test_returns_float(self):
        assert isinstance(c_to_k(0), float)

    def test_invalid_types_raise_value_error(self):
        for bad in ["abc", None, [1, 2], {"x": 1}]:
            with pytest.raises(ValueError):
                c_to_k(bad)

    def test_bool_rejected(self):
        with pytest.raises(ValueError):
            c_to_k(True)

    def test_non_finite_rejected(self):
        for bad in [float("nan"), float("inf"), float("-inf")]:
            with pytest.raises(ValueError):
                c_to_k(bad)


# ---------------------------------------------------------------------------
# Unit tests: round trips / consistency
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", [-273.15, -40.0, -10.0, 0.0, 20.0, 37.0, 100.0])
def test_c_to_f_round_trip(value):
    assert f_to_c(c_to_f(value)) == pytest.approx(value, abs=1e-9)


@pytest.mark.parametrize("value", [-100.0, -40.0, 0.0, 32.0, 98.6, 212.0])
def test_f_to_c_round_trip(value):
    assert c_to_f(f_to_c(value)) == pytest.approx(value, abs=1e-9)


def test_c_to_f_is_inverse_of_f_to_c():
    for value in range(-100, 101, 10):
        assert f_to_c(c_to_f(value)) == pytest.approx(value, abs=1e-9)


# ---------------------------------------------------------------------------
# Schema tests (Pydantic V2, strict)
# ---------------------------------------------------------------------------
class TestSchemas:
    def test_conversion_request_valid_int(self):
        req = ConversionRequest(value=100)
        assert req.value == 100

    def test_conversion_request_valid_float(self):
        req = ConversionRequest(value=20.5)
        assert req.value == pytest.approx(20.5)

    def test_conversion_request_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            ConversionRequest(value=0, junk=1)

    def test_conversion_request_rejects_string(self):
        with pytest.raises(ValidationError):
            ConversionRequest(value="100")

    def test_conversion_request_rejects_nan(self):
        with pytest.raises(ValidationError):
            ConversionRequest(value=float("nan"))

    def test_conversion_request_rejects_inf(self):
        with pytest.raises(ValidationError):
            ConversionRequest(value=float("inf"))

    def test_conversion_request_missing_value(self):
        with pytest.raises(ValidationError):
            ConversionRequest()

    def test_conversion_response_dump(self):
        resp = ConversionResponse(
            from_scale="celsius",
            to_scale="fahrenheit",
            value=0.0,
            result=32.0,
        )
        data = resp.model_dump()
        assert data["from_scale"] == "celsius"
        assert data["to_scale"] == "fahrenheit"
        assert data["value"] == 0.0
        assert data["result"] == 32.0


# ---------------------------------------------------------------------------
# API tests (FastAPI router, direct JSONResponse handling)
# ---------------------------------------------------------------------------
class TestApi:
    def test_health(self, client):
        resp = client.get("/temp-conv/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    @pytest.mark.parametrize(
        "conversion,value,expected",
        [
            ("c-to-f", 0, 32.0),
            ("c-to-f", 100, 212.0),
            ("c-to-f", -40, -40.0),
            ("c-to-f", 20.5, 68.9),
            ("f-to-c", 32, 0.0),
            ("f-to-c", 212, 100.0),
            ("f-to-c", -40, -40.0),
            ("c-to-k", 0, 273.15),
            ("c-to-k", -273.15, 0.0),
            ("c-to-k", 20, 293.15),
        ],
    )
    def test_convert_ok(self, client, conversion, value, expected):
        resp = client.post(f"/temp-conv/convert/{conversion}", json={"value": value})
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] == pytest.approx(expected, abs=1e-9)
        assert "from_scale" in body
        assert "to_scale" in body
        assert "value" in body

    def test_convert_unknown_conversion_returns_400(self, client):
        resp = client.post("/temp-conv/convert/k-to-f", json={"value": 0})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_convert_invalid_body_returns_422(self, client):
        resp = client.post("/temp-conv/convert/c-to-f", json={"value": "abc"})
        assert resp.status_code == 422

    def test_convert_extra_field_returns_422(self, client):
        resp = client.post("/temp-conv/convert/c-to-f", json={"value": 0, "junk": 1})
        assert resp.status_code == 422

    def test_convert_missing_value_returns_422(self, client):
        resp = client.post("/temp-conv/convert/c-to-f", json={})
        assert resp.status_code == 422

    def test_convert_core_error_returns_400(self, client, monkeypatch):
        def boom(value):
            raise ValueError("invalid temperature")

        monkeypatch.setitem(
            _CONVERTERS, "c-to-f", ("celsius", "fahrenheit", boom)
        )
        resp = client.post("/temp-conv/convert/c-to-f", json={"value": 0})
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid temperature"

    def test_convert_internal_error_returns_500(self, client, monkeypatch):
        def boom(value):
            raise RuntimeError("boom")

        monkeypatch.setitem(
            _CONVERTERS, "c-to-f", ("celsius", "fahrenheit", boom)
        )
        resp = client.post("/temp-conv/convert/c-to-f", json={"value": 0})
        assert resp.status_code == 500
        assert resp.json()["error"] == "internal server error"
