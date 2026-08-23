"""Pytest test suite za ``csv_parser`` modul.

Pokriva jedrno logiko (``parse_csv`` / ``to_csv``), robne pogoje (citiranje,
vgrajeni delimiterji, večvrstična polja, prazne vrstice), napake pri
argumentih ter Pydantic V2 sheme (strog validator za delimiter).
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# Uvoz deluje v paketni postavitvi (actions/csv_parser/ kot paket z __init__.py)
# in tudi, če pytest zaganjamo iz drugega korenskega imenika (npr. /work).
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from csv_parser import parse_csv, to_csv
except ImportError:  # pragma: no cover - odvisno od postavitve repozitorija
    from actions.csv_parser import parse_csv, to_csv

try:
    from csv_parser.schemas import (
        CSVParseRequest,
        CSVParseResponse,
        CSVToCsvRequest,
        CSVToCsvResponse,
    )
except ImportError:  # pragma: no cover - odvisno od postavitve repozitorija
    from actions.csv_parser.schemas import (
        CSVParseRequest,
        CSVParseResponse,
        CSVToCsvRequest,
        CSVToCsvResponse,
    )


# ── parse_csv ──────────────────────────────────────────────────────────────

def test_parse_basic():
    assert parse_csv("a,b\nc,d") == [["a", "b"], ["c", "d"]]


def test_parse_custom_delimiter():
    assert parse_csv("a;b;c", delimiter=";") == [["a", "b", "c"]]


def test_parse_quoted_field_with_delimiter():
    assert parse_csv('"a,b",c') == [["a,b", "c"]]


def test_parse_escaped_quotes():
    assert parse_csv('"say ""hi""",x') == [['say "hi"', "x"]]


def test_parse_multiline_quoted_field():
    assert parse_csv('"line1\nline2",x') == [["line1\nline2", "x"]]


def test_parse_skips_blank_lines():
    assert parse_csv("a,b\n\nc,d") == [["a", "b"], ["c", "d"]]


def test_parse_trailing_newline():
    assert parse_csv("a,b\n") == [["a", "b"]]


def test_parse_empty_text():
    assert parse_csv("") == []


def test_parse_single_field():
    assert parse_csv("hello") == [["hello"]]


# ── to_csv ─────────────────────────────────────────────────────────────────

def test_to_csv_basic():
    assert to_csv([["a", "b"], ["c", "d"]]) == "a,b\nc,d"


def test_to_csv_custom_delimiter():
    assert to_csv([["a", "b"]], delimiter=";") == "a;b"


def test_to_csv_quotes_field_containing_delimiter():
    assert to_csv([["a,b", "c"]]) == '"a,b",c'


def test_to_csv_escapes_quotes():
    assert to_csv([['say "hi"', "x"]]) == '"say ""hi""",x'


def test_to_csv_quotes_multiline_field():
    assert to_csv([["line1\nline2"]]) == '"line1\nline2"'


def test_to_csv_empty_rows():
    assert to_csv([]) == ""


def test_to_csv_no_trailing_newline():
    result = to_csv([["a", "b"], ["c", "d"]])
    assert not result.endswith("\n")


def test_to_csv_non_string_cells():
    assert to_csv([[1, 2.5, True, None]]) == "1,2.5,True,None"


def test_to_csv_roundtrip():
    rows = [
        ["a", "b"],
        ["c,d", 'x"y'],
        ["multi\nline", ""],
        ["", "only right"],
    ]
    assert parse_csv(to_csv(rows)) == rows


# ── napake / validacija argumentov ─────────────────────────────────────────

def test_parse_none_text_raises_typeerror():
    with pytest.raises(TypeError):
        parse_csv(None)


def test_parse_none_delimiter_raises_typeerror():
    with pytest.raises(TypeError):
        parse_csv("a,b", delimiter=None)


def test_parse_multi_char_delimiter_raises_valueerror():
    with pytest.raises(ValueError):
        parse_csv("a,b", delimiter="ab")


def test_parse_empty_delimiter_raises_valueerror():
    with pytest.raises(ValueError):
        parse_csv("a,b", delimiter="")


def test_to_csv_none_rows_raises_typeerror():
    with pytest.raises(TypeError):
        to_csv(None)


def test_to_csv_none_delimiter_raises_typeerror():
    with pytest.raises(TypeError):
        to_csv([["a"]], delimiter=None)


def test_to_csv_multi_char_delimiter_raises_valueerror():
    with pytest.raises(ValueError):
        to_csv([["a"]], delimiter=";;")


# ── Pydantic sheme ─────────────────────────────────────────────────────────

def test_parse_request_default_delimiter():
    req = CSVParseRequest(text="a,b")
    assert req.text == "a,b"
    assert req.delimiter == ","


def test_parse_request_custom_delimiter():
    req = CSVParseRequest(text="a;b", delimiter=";")
    assert req.delimiter == ";"


def test_parse_request_invalid_delimiter():
    with pytest.raises(ValidationError):
        CSVParseRequest(text="a,b", delimiter="ab")


def test_to_csv_request_valid():
    req = CSVToCsvRequest(rows=[["a", "b"]], delimiter=";")
    assert req.rows == [["a", "b"]]
    assert req.delimiter == ";"


def test_to_csv_request_invalid_delimiter():
    with pytest.raises(ValidationError):
        CSVToCsvRequest(rows=[["a", "b"]], delimiter="")


def test_response_models():
    resp = CSVParseResponse(rows=[["a"], ["b", "c"]])
    assert resp.rows == [["a"], ["b", "c"]]
    csv_resp = CSVToCsvResponse(text="a,b")
    assert csv_resp.text == "a,b"
