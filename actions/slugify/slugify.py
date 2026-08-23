"""Core Domain Logic — pure URL slug generation.

Directive: `slug(niz)` converts a string into a URL slug:
  * lowercase output
  * spaces (and any other non-alphanumeric characters) become hyphens
  * special characters are removed
  * accented characters are transliterated to their ASCII base form
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# Any run of characters that are not lowercase ASCII letters/digits -> hyphen.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# Collapse consecutive hyphens into a single one.
_DASH_RUN = re.compile(r"-{2,}")
# Strip leading/trailing hyphens.
_EDGE_DASH = re.compile(r"^-+|-+$")


def slug(text: str) -> str:
    """Convert `text` into a URL-friendly slug.

    Examples:
        slug("Hello World")      -> "hello-world"
        slug("Hello, World!")    -> "hello-world"
        slug("  A   B  ")        -> "a-b"
        slug("Café")             -> "cafe"
        slug("")                 -> ""

    Raises:
        TypeError: when `text` is not a string.
    """
    if not isinstance(text, str):
        raise TypeError(f"slug() expects str, got {type(text).__name__!r}")

    # Transliterate accented characters to ASCII (é -> e, ü -> u, ...).
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")

    lowered = ascii_text.lower()
    result = _NON_ALNUM.sub("-", lowered)
    result = _DASH_RUN.sub("-", result)
    result = _EDGE_DASH.sub("", result)
    return result


async def slug_async(text: str) -> str:
    """Async flavour of :func:`slug` (pure async logic, no I/O)."""
    return slug(text)


# Convenience alias so both `slug` and `slugify` are importable.
slugify = slug


__all__ = ["slug", "slug_async", "slugify"]