"""Testi za actions/env_config (parse_env + load_env)."""

import pytest

from actions.env_config import parse_env, load_env


# ------------------------------------------------------------------ #
#  parse_env
# ------------------------------------------------------------------ #
def test_parse_env_basic():
    assert parse_env("A=1\nB=two\n") == {"A": "1", "B": "two"}


def test_parse_env_skips_comments_and_blanks():
    text = "# komentar\n\nA=1\n   \n# drugi\nB=2\n"
    assert parse_env(text) == {"A": "1", "B": "2"}


def test_parse_env_trims_values_and_quotes():
    text = 'A=  "hello world" \nB=\'x\'\nC=plain\n'
    assert parse_env(text) == {"A": "hello world", "B": "x", "C": "plain"}


def test_parse_env_ignores_malformed_lines():
    text = "A=1\nnoequals\n=novalue\n  \nB=2\n"
    assert parse_env(text) == {"A": "1", "B": "2"}


def test_parse_env_empty_text():
    assert parse_env("") == {}
    assert parse_env("# samo komentar\n\n") == {}


def test_parse_env_value_may_contain_equals():
    # Deli se pri prvem '=' — vrednost (npr. URL) lahko vsebuje '='.
    assert parse_env("URL=https://x.com/y?a=b")["URL"] == "https://x.com/y?a=b"


def test_parse_env_duplicate_key_last_wins():
    assert parse_env("A=1\nA=2\n") == {"A": "2"}


# ------------------------------------------------------------------ #
#  load_env
# ------------------------------------------------------------------ #
def test_load_env_reads_file(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\nB=two\n", encoding="utf-8")
    assert load_env(p) == {"A": "1", "B": "two"}


def test_load_env_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_env(tmp_path / "ni.env")
