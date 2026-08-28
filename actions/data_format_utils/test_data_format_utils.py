"""Pytest test suite za actions/data_format_utils (Refaktor 3).

Preveri konsolidirane formatne funkcije: CSV (parse/to), ISO 8601
(parse/format) in deep merge. Plus FastAPI plast.
"""

import pytest
from fastapi.testclient import TestClient

from actions.data_format_utils.formats import (
    deep_merge,
    format_iso,
    parse_csv,
    parse_iso,
    to_csv,
)
from actions.data_format_utils.main import app


# ── CSV ─────────────────────────────────────────────────────────────────────
def test_parse_csv_basic():
    rows = parse_csv("a,b\n1,2\n")
    assert rows == [["a", "b"], ["1", "2"]]


def test_parse_csv_quoted():
    rows = parse_csv('a,b\n"hello, world",2\n')
    assert rows[1] == ["hello, world", "2"]


def test_parse_csv_roundtrip():
    rows = [["a", "b"], ["1", "2"]]
    assert parse_csv(to_csv(rows)) == rows


def test_parse_csv_errors():
    with pytest.raises(ValueError):
        parse_csv("a,b\n", delimiter="ab")


# ── ISO 8601 ────────────────────────────────────────────────────────────────
def test_iso_roundtrip():
    dt = parse_iso("2024-01-15")
    assert format_iso(dt) == "2024-01-15"
    assert dt.hour == 0 and dt.minute == 0


def test_iso_invalid_raises():
    with pytest.raises(ValueError):
        parse_iso("2024-13-45")
    with pytest.raises(ValueError):
        parse_iso("15-01-2024")
    with pytest.raises(ValueError):
        parse_iso("")


# ── Deep merge ──────────────────────────────────────────────────────────────
def test_deep_merge_dicts():
    assert deep_merge({"a": 1, "b": [1]}, {"b": [2], "c": 3}) == {"a": 1, "b": [1, 2], "c": 3}


def test_deep_merge_nested():
    assert deep_merge({"x": {"y": 1}}, {"x": {"z": 2}}) == {"x": {"y": 1, "z": 2}}


def test_deep_merge_scalar_wins():
    assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_endpoints():
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "UP"
    r = client.post("/csv-parse", json={"text": "a,b\n1,2\n"})
    assert r.status_code == 200 and r.json()["rows"] == [["a", "b"], ["1", "2"]]
    r2 = client.post("/iso-parse", json={"value": "2024-01-15"})
    assert r2.json()["value"] == "2024-01-15T00:00:00"
    r3 = client.post("/deep-merge", json={"a": {"x": 1}, "b": {"y": 2}})
    assert r3.json()["merged"] == {"x": 1, "y": 2}
