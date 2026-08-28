"""fleet_sync_test — core domain logic.

Exposes ``mul(a, b)`` returning ``a * b`` (pure Python ``*`` semantics) and an
asyncio-friendly wrapper ``amul``.  The module keeps the core logic dependency
free; strict input validation lives in the Pydantic V2 schemas layer.
"""

from __future__ import annotations

from typing import Any


def mul(a: Any, b: Any) -> Any:
    """Return the product of ``a`` and ``b`` (``a * b``)."""
    return a * b


async def amul(a: Any, b: Any) -> Any:
    """Async wrapper around :func:`mul` — returns ``a * b``."""
    return mul(a, b)


__all__ = ["amul", "mul"]
