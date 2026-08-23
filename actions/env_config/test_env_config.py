"""Pytest testi za modul env_config (parse_env / load_env).

Pokriti robni pogoji: komentarji, prazne vrstice, CRLF, narekovaji,
inline komentarji, vrednosti z ``=`` in ``#``, ``export`` prefiks,
prazne vrednosti, duplikati, branje datotek (str/Path), manjkajoča
datoteka, ne-mutiranje ``os.environ`` ter FastAPI router (če je na voljo).
"""

import os
from pathlib import Path

import pytest

from env_config import load_env, parse_env


# ── parse_env ──────────────────────────────────────────────────────────────

def test_parse_env_basic_pairs():
    assert parse_env("FOO=bar\nBAZ=qux\n") == {"FOO": "bar", "BAZ": "qux"}


def test_parse_env_skips_comments_and_blank_lines():
    text = "# komentar\n\nFOO=bar\n   \n# drugi komentar\nBAR=1\n"
    assert parse_env(text) == {"FOO": "bar", "BAR": "1"}


def test_parse_env_export_prefix():
    assert parse_env("export DB_HOST=localhost\n") == {"DB_HOST": "localhost"}


def test_parse_env_strips_double_and_single_quotes():
    assert parse_env('FOO="bar"\nBAZ=\'qux\'\n') == {"FOO": "bar", "BAZ": "qux"}


def test_parse_env_quoted_value_keeps_spaces_and_hash():
    assert parse_env('FOO="bar # baz"\n') == {"FOO": "bar # baz"}


def test_parse_env_whitespace_around_equals():
    assert parse_env("  FOO  =  bar  \n") == {"FOO": "bar"}


def test_parse_env_empty_value():
    assert parse_env("EMPTY=\n") == {"EMPTY": ""}


def test_parse_env_value_with_equals():
    assert parse_env("KEY=a=b=c\n") == {"KEY": "a=b=c"}


def test_parse_env_inline_comment_unquoted():
    assert parse_env("FOO=bar # komentar\n") == {"FOO": "bar"}


def test_parse_env_hash_without_space_is_kept():
    assert parse_env("URL=https://x.example/path#frag\n") == {
        "URL": "https://x.example/path#frag"
    }


def test_parse_env_crlf_line_endings():
    assert parse_env("FOO=bar\r\nBAZ=qux\r\n") == {"FOO": "bar", "BAZ": "qux"}


def test_parse_env_empty_input():
    assert parse_env("") == {}
    assert parse_env("# samo komentar\n\n") == {}


def test_parse_env_duplicate_key_last_wins():
    assert parse_env("FOO=1\nFOO=2\n") == {"FOO": "2"}


def test_parse_env_does_not_mutate_os_environ():
    before = dict(os.environ)
    parse_env("PATH=/fake\nHOME=/fake\n")
    assert dict(os.environ) == before


# ── load_env ───────────────────────────────────────────────────────────────

def test_load_env_reads_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
    assert load_env(env_file) == {"FOO": "bar", "BAZ": "qux"}


def test_load_env_accepts_string_path(tmp_path: Path):
    env_file = tmp_path / "app.env"
    env_file.write_text("A=1\nB=2\n", encoding="utf-8")
    assert load_env(str(env_file)) == {"A": "1", "B": "2"}


def test_load_env_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_env(tmp_path / "nope.env")


def test_load_env_does_not_apply_to_os_environ(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text("PATH=/tmp/fake\n", encoding="utf-8")
    before = os.environ.get("PATH")
    load_env(env_file)
    assert os.environ.get("PATH") == before


# ── FastAPI router (če so odvisnosti na voljo) ─────────────────────────────

def test_main_router_endpoints():
    pytest.importorskip("fastapi")
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
    except ImportError:  # pragma: no cover
        pytest.skip("fastapi/testclient nista na voljo")

    from env_config.main import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    ok = client.post("/parse", json={"text": "A=1\nB=2\n"})
    assert ok.status_code == 200
    assert ok.json() == {"data": {"A": "1", "B": "2"}, "count": 2}

    missing = client.post("/load", json={"path": "/definitely/not/here/.env"})
    assert missing.status_code == 404

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
