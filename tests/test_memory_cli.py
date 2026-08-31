"""Unit testi za core/memory_cli.py (rob memory / --reset). Uporablja tmp DB."""

import sqlite3

import pytest

from core import memory_cli


def _seed(path, rows=("semantic_memories", "blacklist_patterns", "run_reviews")):
    conn = sqlite3.connect(path)
    for t in rows:
        conn.execute(f"CREATE TABLE IF NOT EXISTS {t} (id INTEGER PRIMARY KEY, x TEXT)")
        conn.execute(f"INSERT INTO {t} (x) VALUES ('a')")
        conn.execute(f"INSERT INTO {t} (x) VALUES ('b')")
    conn.commit()
    conn.close()


def test_show_counts(tmp_path, monkeypatch):
    db = tmp_path / "memory.db"
    _seed(db)
    monkeypatch.setattr(memory_cli, "DB", db)
    counts = memory_cli._count_all()
    assert counts["semantic_memories"] == 2
    assert counts["run_reviews"] == 2
    assert counts["blacklist_patterns"] == 2


def test_reset_clears_all_learning_tables(tmp_path, monkeypatch):
    db = tmp_path / "memory.db"
    _seed(db)
    monkeypatch.setattr(memory_cli, "DB", db)
    assert memory_cli._reset() == 0
    counts = memory_cli._count_all()
    # Sejane tabele so prazne; neobstoječe → -1 (tolerantno, "ni tabele").
    assert counts["semantic_memories"] == 0
    assert counts["blacklist_patterns"] == 0
    assert counts["run_reviews"] == 0


def test_reset_tolerant_to_missing_tables(tmp_path, monkeypatch):
    db = tmp_path / "memory.db"
    sqlite3.connect(db).close()   # prazna baza, brez tabel
    monkeypatch.setattr(memory_cli, "DB", db)
    assert memory_cli._reset() == 0
    assert memory_cli._count_all()["run_reviews"] == -1   # "ni tabele"
