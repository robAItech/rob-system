"""Pytest test suite for chat_detect_test.tri()."""

import sys
from pathlib import Path

# Make the module importable both as a top-level package and as an
# ``actions.*`` subpackage, regardless of how pytest is invoked.
_ACTIONS_DIR = Path(__file__).resolve().parent.parent
if str(_ACTIONS_DIR) not in sys.path:
    sys.path.insert(0, str(_ACTIONS_DIR))

try:
    from chat_detect_test import tri
except ImportError:  # pragma: no cover - fallback for actions.* layout
    from actions.chat_detect_test import tri


def test_tri_returns_known_value():
    assert tri() == 3


def test_tri_returns_int():
    assert isinstance(tri(), int)


def test_tri_is_callable():
    assert callable(tri)


def test_tri_is_consistent():
    # Roundtrip/known-value sanity: repeated calls yield the same result.
    assert tri() == tri() == 3
    assert tri() + tri() == 6
