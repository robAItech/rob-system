"""Pytest test suite for the ``ini_config`` module.

Verifies the documented behaviour of :func:`parse_ini` and :func:`read_ini`:

* comments start with ``#`` or ``;`` (full-line and trailing);
* keys and values are separated by ``=``, ``:`` or whitespace;
* quoted values may contain ``#``/``;`` literally;
* duplicate sections are merged, duplicate keys are overwritten;
* lines before the first section belong to the empty-string section.
"""

from __future__ import annotations

import pytest

try:  # package imported from its parent directory (actions/)
    from ini_config import parse_ini, read_ini
except ImportError:  # pragma: no cover - depends on pytest import mode
    from actions.ini_config import parse_ini, read_ini


# ---------------------------------------------------------------------------
# parse_ini — document structure
# ---------------------------------------------------------------------------


def test_empty_text_returns_empty_document() -> None:
    assert parse_ini("") == {}


def test_whitespace_only_text_returns_empty_document() -> None:
    assert parse_ini("  \n\t\n  ") == {}


def test_comment_only_text_returns_empty_document() -> None:
    assert parse_ini("# full line\n; another comment\n  # indented\n") == {}


def test_single_section_with_key_value() -> None:
    assert parse_ini("[server]\nhost=localhost\n") == {
        "server": {"host": "localhost"}
    }


def test_multiple_sections() -> None:
    text = "[a]\nx=1\n[b]\ny=2\n"
    assert parse_ini(text) == {"a": {"x": "1"}, "b": {"y": "2"}}


def test_lines_before_first_section_belong_to_empty_section() -> None:
    text = "title=hello\n[sec]\nkey=value\n"
    assert parse_ini(text) == {"": {"title": "hello"}, "sec": {"key": "value"}}


def test_section_without_body() -> None:
    assert parse_ini("[empty]\n") == {"empty": {}}


def test_section_header_whitespace_is_stripped() -> None:
    assert parse_ini("  [  spaced  ]  \nk=v\n") == {"spaced": {"k": "v"}}


def test_duplicate_sections_are_merged() -> None:
    text = "[s]\na=1\n[s]\nb=2\n"
    assert parse_ini(text) == {"s": {"a": "1", "b": "2"}}


def test_duplicate_keys_are_overwritten() -> None:
    assert parse_ini("[s]\na=1\na=2\n") == {"s": {"a": "2"}}


# ---------------------------------------------------------------------------
# parse_ini — separators and values
# ---------------------------------------------------------------------------


def test_equals_separator() -> None:
    assert parse_ini("[s]\nkey=value\n") == {"s": {"key": "value"}}


def test_colon_separator() -> None:
    assert parse_ini("[s]\nkey: value\n") == {"s": {"key": "value"}}


def test_whitespace_separator() -> None:
    assert parse_ini("[s]\nkey value\n") == {"s": {"key": "value"}}


def test_key_without_value() -> None:
    assert parse_ini("[s]\nflag\n") == {"s": {"flag": ""}}


def test_value_whitespace_is_stripped() -> None:
    assert parse_ini("[s]\nkey =   padded   \n") == {"s": {"key": "padded"}}


def test_trailing_hash_comment_is_stripped() -> None:
    assert parse_ini("[s]\nkey=value # comment\n") == {"s": {"key": "value"}}


def test_trailing_semicolon_comment_is_stripped() -> None:
    assert parse_ini("[s]\nkey=value ; comment\n") == {"s": {"key": "value"}}


def test_quoted_value_keeps_hash_literal() -> None:
    assert parse_ini('[s]\nkey="a#b"\n') == {"s": {"key": '"a#b"'}}


def test_quoted_value_keeps_semicolon_literal() -> None:
    assert parse_ini("[s]\nkey='a;b'\n") == {"s": {"key": "'a;b'"}}


def test_empty_key_is_skipped() -> None:
    assert parse_ini("[s]\n=orphan\n") == {"s": {}}


# ---------------------------------------------------------------------------
# parse_ini — input validation
# ---------------------------------------------------------------------------


def test_non_string_input_raises_type_error() -> None:
    with pytest.raises(TypeError):
        parse_ini(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        parse_ini(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# read_ini
# ---------------------------------------------------------------------------


def test_read_ini_parses_file(tmp_path) -> None:
    ini_file = tmp_path / "config.ini"
    ini_file.write_text("[db]\nhost=db.internal\nport=5432\n", encoding="utf-8")
    assert read_ini(ini_file) == {"db": {"host": "db.internal", "port": "5432"}}


def test_read_ini_accepts_str_path(tmp_path) -> None:
    ini_file = tmp_path / "app.ini"
    ini_file.write_text("k=v\n", encoding="utf-8")
    assert read_ini(str(ini_file)) == {"": {"k": "v"}}


def test_read_ini_missing_file_raises_file_not_found(tmp_path) -> None:
    missing = tmp_path / "does_not_exist.ini"
    with pytest.raises(FileNotFoundError):
        read_ini(missing)
