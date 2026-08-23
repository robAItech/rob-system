"""json_deep_merge — recursive deep merge for JSON-like structures.

The single public entry point is :func:`deep_merge`.  Merge semantics:

- ``dict`` vs ``dict``  → keys are merged recursively; ``b`` wins on conflicts
- ``list`` vs ``list``  → the two lists are concatenated (``a`` items first)
- anything else (scalars, ``None``, mixed types) → ``b`` wins

Inputs are never mutated; a brand-new merged structure is returned.
"""

from __future__ import annotations

from typing import Any


def deep_merge(a: Any, b: Any) -> Any:
    """Recursively merge ``b`` into ``a`` and return the merged result.

    Args:
        a: Base JSON-like value (usually a ``dict``).
        b: Overlay JSON-like value; its values win on conflicts.

    Returns:
        A new merged structure.  Neither ``a`` nor ``b`` is modified.

    Examples:
        >>> deep_merge({"a": 1, "b": [1]}, {"b": [2], "c": 3})
        {'a': 1, 'b': [1, 2], 'c': 3}
        >>> deep_merge({"x": {"y": 1}}, {"x": {"z": 2}})
        {'x': {'y': 1, 'z': 2}}
        >>> deep_merge({"a": 1}, {"a": 2})
        {'a': 2}
    """
    # Both sides are dicts -> merge recursively, key by key.
    if isinstance(a, dict) and isinstance(b, dict):
        merged: dict[Any, Any] = {}
        for key in set(a) | set(b):
            if key in a and key in b:
                merged[key] = deep_merge(a[key], b[key])
            elif key in a:
                merged[key] = a[key]
            else:
                merged[key] = b[key]
        return merged

    # Both sides are lists -> concatenate (a's items first, then b's).
    if isinstance(a, list) and isinstance(b, list):
        return a + b

    # Anything else (scalars, None, mixed types) -> b wins.
    return b