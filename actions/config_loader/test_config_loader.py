"""test_config_loader.py — port originalnih testov (env_config + ini_config + config_manager).

Test-Locked: daemon ga ne sme spreminjati. Kodira zahtevano semantiko
konsolidiranega modula config_loader.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from actions.config_loader import (ConfigManager, load_env, merge_env,
                                   parse_env, parse_ini, read_ini)


# ── parse_env ───────────────────────────────────────────────────────────── #
def test_parse_env_osnovno():
    assert parse_env("A=1\nB=x") == {"A": "1", "B": "x"}


def test_parse_env_preskoci_komentarje_in_prazno():
    assert parse_env("# komentar\n\n  \nA=1") == {"A": "1"}


def test_parse_env_export_prefiks():
    assert parse_env("export A=1") == {"A": "1"}


def test_parse_env_prvi_znak_je_locevalo():
    assert parse_env("URL=http://x.example/path") == {"URL": "http://x.example/path"}


def test_parse_env_narekovaji_dobesedno():
    assert parse_env("A=\"vsebina # s \"""\nB='bar # baz'") == {"A": "vsebina # s ", "B": "bar # baz"}


def test_parse_env_inline_komentar_se_odstrani():
    assert parse_env("A=1 # komentar") == {"A": "1"}


def test_parse_env_hash_brez_presledka_ostane():
    assert parse_env("A=foo#bar") == {"A": "foo#bar"}


def test_parse_env_zadnja_pojavitev_zmaga():
    assert parse_env("A=1\nA=2") == {"A": "2"}


def test_parse_env_ne_mutira_os_environ(monkeypatch):
    import os
    monkeypatch.setattr(os, "environ", {"PRE": "x"})
    parse_env("PRE=new")
    assert os.environ["PRE"] == "x"


def test_load_env_prebere_datoteko(tmp_path):
    f = tmp_path / ".env"
    f.write_text("A=1\nB=two\n", encoding="utf-8")
    assert load_env(f) == {"A": "1", "B": "two"}


def test_load_env_manjkajoca_pada():
    with pytest.raises(FileNotFoundError):
        load_env(Path("/ne/obstaja/.env"))


# ── parse_ini ───────────────────────────────────────────────────────────── #
def test_parse_ini_osnovno():
    ini = "[db]\nhost=localhost\nport=5432\n[app]\ndebug=true"
    assert parse_ini(ini) == {"db": {"host": "localhost", "port": "5432"},
                              "app": {"debug": "true"}}


def test_parse_ini_komentarji():
    assert parse_ini("# komentar\n; tudi\n[sec]\na=1") == {"sec": {"a": "1"}}


def test_parse_ini_dvopicje_locevalo():
    assert parse_ini("[sec]\nkey: value") == {"sec": {"key": "value"}}


def test_parse_ini_vrstice_pred_sekcijo_gredo_v_prazno_sekcijo():
    assert parse_ini("top=1\n[sec]\na=2") == {"": {"top": "1"}, "sec": {"a": "2"}}


def test_parse_ini_ponovljene_sekcije_se_zdruzijo():
    assert parse_ini("[s]\na=1\n[s]\nb=2") == {"s": {"a": "1", "b": "2"}}


def test_parse_ini_ponovljen_kljuc_se_prepise():
    assert parse_ini("[s]\na=1\na=2") == {"s": {"a": "2"}}


def test_parse_ini_ne_str_pada():
    with pytest.raises(TypeError):
        parse_ini(123)


def test_read_ini_prebere_datoteko(tmp_path):
    f = tmp_path / "c.ini"
    f.write_text("[sec]\na=1\n", encoding="utf-8")
    assert read_ini(f) == {"sec": {"a": "1"}}


def test_read_ini_manjkajoca_pada():
    with pytest.raises(FileNotFoundError):
        read_ini(Path("/ne/obstaja/x.ini"))


# ── ConfigManager / merge_env ───────────────────────────────────────────── #
def test_config_manager_merge_po_prioriteti():
    cm = ConfigManager({"a": "1", "b": "x"}, {"b": "2"})
    assert cm.all() == {"a": "1", "b": "2"}   # later wins
    assert cm.get("a") == "1"
    assert cm.get("b") == "2"
    assert cm.get("zz", "privzeto") == "privzeto"


def test_config_manager_contains_len_items():
    cm = ConfigManager({"a": "1"})
    assert "a" in cm
    assert "b" not in cm
    assert len(cm) == 1
    assert dict(cm.items()) == {"a": "1"}


def test_config_manager_accepts_raw_env_string():
    cm = ConfigManager("A=1\nB=x")
    assert cm.get("A") == "1"
    assert cm.get("B") == "x"


def test_config_manager_accepts_env_file_path(tmp_path):
    f = tmp_path / "c.env"
    f.write_text("K=v\n", encoding="utf-8")
    cm = ConfigManager(str(f))
    assert cm.get("K") == "v"


def test_merge_env():
    assert merge_env({"a": "1"}, {"b": "2"}, {"a": "9"}) == {"a": "9", "b": "2"}
