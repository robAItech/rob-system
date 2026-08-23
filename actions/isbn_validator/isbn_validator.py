"""actions/isbn_validator/isbn_validator.py — Core domain logic for ISBN validation.

Pure, dependency-free validation of ISBN-10 and ISBN-13 identifiers using the
official checksum algorithms defined by ISO 2108:

* ISBN-10:  sum(i * d_i for i in 1..10) % 11 == 0, where the check digit may be
  ``X``/``x`` (value 10) in the last position.
* ISBN-13:  sum(d_i * (1 if i is even else 3)) % 10 == 0.

Hyphens and whitespace are accepted as *group separators* between digits and are
stripped before the checksum is computed. Whitespace framing the whole value on
*both* sides is treated as a formatting frame and also stripped. A separator
that dangles at the very start or end of the value (e.g. a lone trailing space)
is a formatting error and is rejected. Non-string input is treated as invalid
(returns False).
"""

from __future__ import annotations

__all__ = [
    "is_valid_isbn",
    "is_valid_isbn10",
    "is_valid_isbn13",
    "is_valid_isbn_async",
    "is_valid_isbn10_async",
    "is_valid_isbn13_async",
]

#: Formatting characters accepted as group separators between digits.
_SEPARATORS = frozenset(" \t\n\r\v\f-")


def _normalize(value: object) -> str:
    """Return a canonical digit string, or an empty string for non-str input.

    * Hyphens and whitespace strictly *between* characters act as group
      separators and are removed.
    * Whitespace framing the whole value on *both* sides is stripped.
    * A separator at the very beginning or end of the value (e.g. a lone
      trailing space) is preserved so that the downstream length/checksum
      checks reject the string as malformed.
    """
    if not isinstance(value, str):
        return ""
    text = value
    # A whitespace frame on *both* sides is a formatting convenience and is
    # removed; a one-sided (e.g. trailing-only) separator is a formatting
    # error and must survive so validation rejects it.
    if text and text[0].isspace() and text[-1].isspace():
        text = text.strip()
    # Locate the first/last non-separator characters: anything outside that
    # core (dangling separators) is preserved verbatim.
    left = 0
    while left < len(text) and text[left] in _SEPARATORS:
        left += 1
    right = len(text)
    while right > left and text[right - 1] in _SEPARATORS:
        right -= 1
    core = "".join(text[left:right].split()).replace("-", "")
    return text[:left] + core + text[right:]


def _is_ascii_digits(text: str) -> bool:
    """True if every character is an ASCII digit (0-9)."""
    return text.isascii() and text.isdigit()


def _is_valid_isbn10_digits(digits: str) -> bool:
    if len(digits) != 10:
        return False
    # First nine characters must be digits; the last may be a digit or X (10).
    if not _is_ascii_digits(digits[:9]):
        return False
    if digits[9] not in "0123456789Xx":
        return False
    total = 0
    for i, ch in enumerate(digits, start=1):
        value = 10 if ch in ("X", "x") else int(ch)
        total += i * value
    return total % 11 == 0


def _is_valid_isbn13_digits(digits: str) -> bool:
    if len(digits) != 13 or not _is_ascii_digits(digits):
        return False
    total = 0
    for i, ch in enumerate(digits):
        total += int(ch) * (1 if i % 2 == 0 else 3)
    return total % 10 == 0


def is_valid_isbn10(value: object) -> bool:
    """Return True if ``value`` is a valid ISBN-10 (checksum OK).

    Accepts canonical digit strings as well as strings with group separators
    (spaces/tabs/hyphens) between digits, and whitespace framing the whole
    value on both sides.
    """
    return _is_valid_isbn10_digits(_normalize(value))


def is_valid_isbn13(value: object) -> bool:
    """Return True if ``value`` is a valid ISBN-13 (checksum OK).

    Accepts canonical digit strings as well as strings with group separators
    (spaces/tabs/hyphens) between digits, and whitespace framing the whole
    value on both sides.
    """
    return _is_valid_isbn13_digits(_normalize(value))


def is_valid_isbn(value: object) -> bool:
    """Return True if ``value`` is a valid ISBN-10 or ISBN-13."""
    return is_valid_isbn10(value) or is_valid_isbn13(value)


async def is_valid_isbn10_async(value: object) -> bool:
    """Async wrapper around :func:`is_valid_isbn10`."""
    return is_valid_isbn10(value)


async def is_valid_isbn13_async(value: object) -> bool:
    """Async wrapper around :func:`is_valid_isbn13`."""
    return is_valid_isbn13(value)


async def is_valid_isbn_async(value: object) -> bool:
    """Async wrapper around :func:`is_valid_isbn`."""
    return is_valid_isbn(value)