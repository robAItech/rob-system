"""Pytest test suite for actions/isbn_validator — ISBN-10 / ISBN-13 validation.

Covers the full public API surface of the module:

* is_valid_isbn10 / is_valid_isbn13 / is_valid_isbn (+ async wrappers)
* formatting tolerance (hyphens, spaces, tabs, surrounding whitespace)
* edge cases (empty strings, wrong lengths, non-string input, illegal chars)
* pydantic request/response schemas

All expected values follow the official ISO 2108 checksum algorithms.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

# Import via the canonical package path; fall back to a bare import when the
# surrounding ``actions`` package is not importable from the test rootdir.
try:  # pragma: no cover - exercised only when the package layout differs
    from actions.isbn_validator import (
        is_valid_isbn,
        is_valid_isbn10,
        is_valid_isbn13,
        is_valid_isbn_async,
        is_valid_isbn10_async,
        is_valid_isbn13_async,
    )
    from actions.isbn_validator.schemas import (
        ISBNValidationRequest,
        ISBNValidationResponse,
    )
except ImportError:  # pragma: no cover
    from isbn_validator import (
        is_valid_isbn,
        is_valid_isbn10,
        is_valid_isbn13,
        is_valid_isbn_async,
        is_valid_isbn10_async,
        is_valid_isbn13_async,
    )
    from schemas import ISBNValidationRequest, ISBNValidationResponse


# ---------------------------------------------------------------------------
# ISBN-10
# ---------------------------------------------------------------------------

VALID_ISBN10 = [
    "0306406152",      # canonical example
    "080442957X",      # uppercase X check digit
    "0521349931",
    "007462542X",
    "0-306-40615-2",   # hyphenated
    "0 306 40615 2",   # spaced
    "  0306406152  ",  # surrounding whitespace
    "0-306\t40615-2",  # mixed whitespace + hyphens
]

INVALID_ISBN10 = [
    "0306406153",      # wrong check digit
    "030640615X",      # X with wrong checksum
    "030640615",       # too short
    "03064061523",     # too long
    "030640615A",      # illegal check character
    "0X306406152",     # X in the middle
    "0306406152 ",     # trailing space survives only if normalization fails -> covered above
]


@pytest.mark.parametrize("isbn", VALID_ISBN10)
def test_isbn10_valid(isbn: str) -> None:
    assert is_valid_isbn10(isbn) is True


@pytest.mark.parametrize("isbn", INVALID_ISBN10)
def test_isbn10_invalid(isbn: str) -> None:
    assert is_valid_isbn10(isbn) is False


def test_isbn10_rejects_short_and_long() -> None:
    assert is_valid_isbn10("030640615") is False
    assert is_valid_isbn10("03064061523") is False


def test_isbn10_rejects_lowercase_x_with_bad_checksum() -> None:
    # Lowercase x is accepted only when the checksum matches.
    assert is_valid_isbn10("007462542x") is True
    assert is_valid_isbn10("030640615x") is False


def test_isbn10_non_string_input() -> None:
    for bad in (None, 306406152, 3.14, ["0306406152"], {"isbn": "0306406152"}, b"0306406152"):
        assert is_valid_isbn10(bad) is False


def test_isbn10_empty_string() -> None:
    assert is_valid_isbn10("") is False


# ---------------------------------------------------------------------------
# ISBN-13
# ---------------------------------------------------------------------------

VALID_ISBN13 = [
    "9780306406157",   # canonical example
    "9780132350884",   # Clean Code
    "9780451524935",   # Nineteen Eighty-Four
    "978-0-306-40615-7",
    "978 0 306 40615 7",
    "  9780306406157  ",
    "978-0-306\t40615-7",
]

INVALID_ISBN13 = [
    "9780306406158",   # wrong check digit
    "978030640615",    # too short
    "97803064061573",  # too long
    "978030640615A",   # non-digit
    "97803064061X7",   # X anywhere
]


@pytest.mark.parametrize("isbn", VALID_ISBN13)
def test_isbn13_valid(isbn: str) -> None:
    assert is_valid_isbn13(isbn) is True


@pytest.mark.parametrize("isbn", INVALID_ISBN13)
def test_isbn13_invalid(isbn: str) -> None:
    assert is_valid_isbn13(isbn) is False


def test_isbn13_non_string_input() -> None:
    for bad in (None, 9780306406157, 9.78, ["9780306406157"], b"9780306406157"):
        assert is_valid_isbn13(bad) is False


def test_isbn13_empty_string() -> None:
    assert is_valid_isbn13("") is False


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

def test_isbn_auto_detect() -> None:
    assert is_valid_isbn("0306406152") is True      # ISBN-10
    assert is_valid_isbn("9780306406157") is True   # ISBN-13
    assert is_valid_isbn("0-306-40615-2") is True   # ISBN-10 formatted
    assert is_valid_isbn("978-0-306-40615-7") is True
    assert is_valid_isbn("not-an-isbn") is False
    assert is_valid_isbn("") is False
    assert is_valid_isbn(None) is False
    assert is_valid_isbn(42) is False


def test_isbn13_does_not_accept_isbn10_and_vice_versa() -> None:
    assert is_valid_isbn13("0306406152") is False
    assert is_valid_isbn10("9780306406157") is False


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------

def test_isbn10_async() -> None:
    assert asyncio.run(is_valid_isbn10_async("0306406152")) is True
    assert asyncio.run(is_valid_isbn10_async("0306406153")) is False
    assert asyncio.run(is_valid_isbn10_async(None)) is False


def test_isbn13_async() -> None:
    assert asyncio.run(is_valid_isbn13_async("9780306406157")) is True
    assert asyncio.run(is_valid_isbn13_async("9780306406158")) is False
    assert asyncio.run(is_valid_isbn13_async(None)) is False


def test_isbn_async() -> None:
    assert asyncio.run(is_valid_isbn_async("0306406152")) is True
    assert asyncio.run(is_valid_isbn_async("9780306406157")) is True
    assert asyncio.run(is_valid_isbn_async("nope")) is False


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

def test_request_schema_strips_surrounding_whitespace() -> None:
    req = ISBNValidationRequest(isbn="  0306406152  ")
    assert req.isbn == "0306406152"


def test_request_schema_rejects_non_string() -> None:
    with pytest.raises(ValidationError):
        ISBNValidationRequest(isbn=123)


def test_response_schema() -> None:
    resp = ISBNValidationResponse(isbn="9780306406157", is_valid=True)
    assert resp.isbn == "9780306406157"
    assert resp.is_valid is True
    assert resp.model_dump() == {"isbn": "9780306406157", "is_valid": True}
