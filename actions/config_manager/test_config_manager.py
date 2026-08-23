"""Pytest test suite for actions.config_manager."""

import os
from pathlib import Path

import pytest

try:
    from actions.config_manager import ConfigManager, merge_env
except ImportError:  # pragma: no cover - cwd fallback
    from config_manager import ConfigManager, merge_env


def test_empty_manager():
    cm = ConfigManager()
    assert cm.all() == {}
    assert cm.get("MISSING") is None


def test_single_source_string():
    cm = ConfigManager("FOO=bar\nBAZ=qux\n")
    assert cm.get("FOO") == "bar"
    assert cm.get("BAZ") == "qux"
    assert cm.all() == {"FOO": "bar", "BAZ": "qux"}


def test_later_source_wins():
    cm = ConfigManager("FOO=1\nBAR=2\n", "FOO=10\nBAR=20\nBAZ=30\n")
    assert cm.get("FOO") == "10"
    assert cm.get("BAR") == "20"
    assert cm.get("BAZ") == "30"


def test_merge_multiple_sources():
    cm = ConfigManager("A=1\n", "B=2\n", "C=3\n")
    assert cm.all() == {"A": "1", "B": "2", "C": "3"}


def test_dict_source_later_wins():
    cm = ConfigManager({"X": "1"}, {"X": "2", "Y": "3"})
    assert cm.get("X") == "2"
    assert cm.get("Y") == "3"


def test_file_path_sources(tmp_path):
    first = tmp_path / "one.env"
    second = tmp_path / "two.env"
    first.write_text("K1=v1\nK2=v2\n", encoding="utf-8")
    second.write_text("K2=v2b\nK3=v3\n", encoding="utf-8")
    cm = ConfigManager(first, second)
    assert cm.get("K1") == "v1"
    assert cm.get("K2") == "v2b"
    assert cm.get("K3") == "v3"


def test_comments_and_blank_lines_ignored():
    cm = ConfigManager("# comment line\n\nFOO=bar\n")
    assert cm.get("FOO") == "bar"
    assert cm.get("MISSING") is None
    assert "# comment line" not in cm.all()


def test_get_with_default():
    cm = ConfigManager("FOO=bar\n")
    assert cm.get("NOPE", "fallback") == "fallback"
    assert cm.get("FOO", "fallback") == "bar"


def test_all_returns_copy():
    cm = ConfigManager("FOO=bar\n")
    snapshot = cm.all()
    snapshot["HACKED"] = "1"
    assert cm.get("HACKED") is None


def test_contains_and_len():
    cm = ConfigManager("FOO=bar\n")
    assert "FOO" in cm
    assert "NOPE" not in cm
    assert len(cm) == 1


def test_merge_env_helper():
    merged = merge_env("A=1\n", "A=2\nB=3\n")
    assert merged == {"A": "2", "B": "3"}


def test_package_reexports():
    try:
        import actions.config_manager as pkg
    except ImportError:  # pragma: no cover - actions pkg not on path here
        pytest.skip("actions package not importable from this cwd")
    assert pkg.ConfigManager is ConfigManager
    assert callable(pkg.parse_env)
