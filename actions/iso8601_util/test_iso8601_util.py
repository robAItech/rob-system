"""Pytest testi za modul iso8601_util.

Pokrivajo:
- jedro: parse_iso / format_iso (veljavni vhodi, robni pogoji, neveljavni vhodi),
- povratno pretvorbo (round-trip),
- Pydantic V2 sheme s strogimi validatorji,
- FastAPI router (JSONResponse 4xx/5xx handling; preskočeno, če httpx manjka).
"""

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from iso8601_util import format_iso, parse_iso
from iso8601_util.schemas import IsoDateRequest, IsoDateTimeRequest, IsoDateResponse


# ---------------------------------------------------------------------------
# parse_iso
# ---------------------------------------------------------------------------

class TestParseIso:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2024-01-15", datetime(2024, 1, 15)),
            ("2000-01-01", datetime(2000, 1, 1)),
            ("1999-12-31", datetime(1999, 12, 31)),
            ("2024-12-31", datetime(2024, 12, 31)),
            ("2024-02-29", datetime(2024, 2, 29)),  # prestopno leto
            ("2023-02-28", datetime(2023, 2, 28)),
            ("1900-01-01", datetime(1900, 1, 1)),
            ("9999-12-31", datetime(9999, 12, 31)),
        ],
    )
    def test_valid_dates(self, value, expected):
        assert parse_iso(value) == expected

    def test_returns_datetime_at_midnight(self):
        dt = parse_iso("2024-01-15")
        assert isinstance(dt, datetime)
        assert (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "2024-13-01",       # neobstoječ mesec
            "2024-00-10",       # mesec 0
            "2024-01-00",       # dan 0
            "2023-02-29",       # neprestopno leto
            "2024-04-31",       # april nima 31 dni
            "2024/01/15",       # napačen ločilnik
            "15-01-2024",       # obrnjen vrstni red
            "2024-1-5",         # manjkajoče vodilne ničle
            "2024-01-15T10:30:00",  # čas ni del formata YYYY-MM-DD
            "20240115",         # brez ločil
            "not-a-date",
            "2024-01-15 ",
            " 2024-01-15",
            "0000-01-01",       # leto 0 ni veljavno
        ],
    )
    def test_invalid_raises_value_error(self, value):
        with pytest.raises(ValueError):
            parse_iso(value)

    @pytest.mark.parametrize("value", [None, 20240115, 42, 3.14, ["2024-01-15"]])
    def test_non_string_raises_value_error(self, value):
        with pytest.raises(ValueError):
            parse_iso(value)


# ---------------------------------------------------------------------------
# format_iso
# ---------------------------------------------------------------------------

class TestFormatIso:
    @pytest.mark.parametrize(
        ("dt", "expected"),
        [
            (datetime(2024, 1, 15), "2024-01-15"),
            (datetime(2024, 1, 15, 23, 59, 59), "2024-01-15"),  # čas se izpusti
            (datetime(2023, 2, 28), "2023-02-28"),
            (datetime(2024, 2, 29), "2024-02-29"),
            (datetime(2000, 12, 31, 0, 0, 0), "2000-12-31"),
        ],
    )
    def test_datetime_formats(self, dt, expected):
        assert format_iso(dt) == expected

    def test_date_object(self):
        assert format_iso(date(2024, 1, 15)) == "2024-01-15"

    def test_returns_str(self):
        assert isinstance(format_iso(datetime(2024, 1, 15)), str)

    @pytest.mark.parametrize("value", ["2024-01-15", 20240115, 42, 3.14, None, ["x"]])
    def test_non_date_raises_type_error(self, value):
        with pytest.raises(TypeError):
            format_iso(value)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    @pytest.mark.parametrize(
        "value",
        [
            "2024-01-15",
            "1999-12-31",
            "2024-02-29",
            "2000-01-01",
            "9999-12-31",
        ],
    )
    def test_parse_format_round_trip(self, value):
        assert format_iso(parse_iso(value)) == value


# ---------------------------------------------------------------------------
# Pydantic V2 sheme (strogi validatorji)
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_iso_date_request_valid(self):
        req = IsoDateRequest(value="2024-01-15")
        assert req.value == "2024-01-15"

    @pytest.mark.parametrize("value", ["2024-13-01", "2023-02-29", "hello", "", "2024-1-5"])
    def test_iso_date_request_invalid_raises(self, value):
        with pytest.raises(ValidationError):
            IsoDateRequest(value=value)

    def test_iso_datetime_request_valid(self):
        req = IsoDateTimeRequest(value="2024-01-15T10:30:00")
        assert req.value == "2024-01-15T10:30:00"

    @pytest.mark.parametrize("value", ["garbage", "2024-13-01T10:00:00", ""])
    def test_iso_datetime_request_invalid_raises(self, value):
        with pytest.raises(ValidationError):
            IsoDateTimeRequest(value=value)

    def test_iso_date_response(self):
        resp = IsoDateResponse(value="2024-01-15T00:00:00")
        assert resp.value == "2024-01-15T00:00:00"


# ---------------------------------------------------------------------------
# FastAPI router (JSONResponse 4xx/5xx handling)
# ---------------------------------------------------------------------------

try:
    from fastapi.testclient import TestClient

    from iso8601_util.main import app, router

    HAS_HTTPX = True
except ImportError:  # pragma: no cover - TestClient zahteva httpx
    HAS_HTTPX = False


@pytest.mark.skipif(not HAS_HTTPX, reason="httpx ni na voljo (TestClient)")
class TestAPI:
    @pytest.fixture()
    def client(self):
        return TestClient(app)

    def test_health(self, client):
        resp = client.get("/iso8601/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_parse_valid(self, client):
        resp = client.post("/iso8601/parse", json={"value": "2024-01-15"})
        assert resp.status_code == 200
        assert resp.json()["value"] == "2024-01-15T00:00:00"

    def test_parse_invalid_returns_4xx(self, client):
        resp = client.post("/iso8601/parse", json={"value": "2024-13-01"})
        assert 400 <= resp.status_code < 500

    def test_format_valid(self, client):
        resp = client.post(
            "/iso8601/format", json={"value": "2024-01-15T10:30:00"}
        )
        assert resp.status_code == 200
        assert resp.json()["value"] == "2024-01-15"

    def test_format_date_only(self, client):
        resp = client.post("/iso8601/format", json={"value": "2024-01-15"})
        assert resp.status_code == 200
        assert resp.json()["value"] == "2024-01-15"

    def test_format_invalid_returns_4xx(self, client):
        resp = client.post("/iso8601/format", json={"value": "garbage"})
        assert 400 <= resp.status_code < 500

    def test_router_exposed(self):
        assert router.prefix == "/iso8601"
