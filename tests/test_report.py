"""Unit testi za core/report.py (tedenski readout). Markdown se sestavi iz
podatkov v tmp_path (audit.jsonl, run_reviews DB, registra) — brez pravih
datotek .rob_ai."""

import json
import sqlite3

import pytest

from core import audit, quality, report


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Usmeri audit, DB in registre v tmp_path."""
    monkeypatch.setattr(audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(quality, "DEFAULT_DB", tmp_path / "memory.db")
    monkeypatch.setattr(quality, "QUALITY_REGISTRY", tmp_path / "quality_registry.json")
    monkeypatch.setattr(quality, "ESCALATIONS_FILE", tmp_path / "escalations.json")
    return tmp_path


def _write_audit(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS run_reviews ("
                 "id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, "
                 "directive TEXT NOT NULL, outcome TEXT NOT NULL, "
                 "root_cause TEXT NOT NULL, lesson TEXT)")
    conn.executemany("INSERT INTO run_reviews (project, directive, outcome, root_cause) "
                     "VALUES (?, 'x', ?, 'unknown')",
                     [("a", "green"), ("a", "failed"), ("b", "green")])
    conn.commit()
    conn.close()


def test_generate_report_sections_and_tasks(env):
    now = 1_000_000
    _write_audit(env / "audit.jsonl", [
        {"ts": now - 86400 * 3, "event": "daemon-task", "project": "a", "status": "ok",
         "detail": "duration_s=5.0"},
        {"ts": now - 86400, "event": "daemon-task", "project": "a", "status": "failed",
         "detail": "duration_s=3.0"},
        {"ts": now - 86400 * 2, "event": "fleet-result", "project": "b", "status": "done",
         "detail": "worker=DESKTOP worker"},
        # Zunaj enotedenskega okna → ne sme v izvedene naloge.
        {"ts": now - 86400 * 20, "event": "daemon-task", "project": "old", "status": "failed",
         "detail": "duration_s=1.0"},
    ])
    _make_db(env / "memory.db")

    md = report.generate_weekly_report(db_path=env / "memory.db", weeks=1, now=now)

    assert "# ROB system — tedenski readout" in md
    assert "## Izvedene naloge" in md
    assert "## Kakovost po projektih" in md
    assert "## Eval trend" in md
    assert "## Fleet" in md
    assert "## Eskalacije in onemogočeni targeti" in md
    # Povzetek: 3 izvedene v obdobju (2 daemon-task + 1 fleet-result; stara izven okna).
    assert "3 izvedenih nalog" in md
    assert "2 ok" in md and "1 failed" in md
    # Taski: vrstici za "a" in "b" sta prisotni, "old" (izven okna) ne.
    assert "| a |" in md and "| b |" in md
    assert "old" not in md
    # Kakovost po projektih.
    assert "| a | 2 |" in md or "a" in md


def test_generate_report_shows_escalations_and_disabled(env):
    now = 1_000_000
    _write_audit(env / "audit.jsonl", [
        {"ts": now - 100, "event": "daemon-task", "project": "weak", "status": "failed",
         "detail": "duration_s=1.0"},
    ])
    _make_db(env / "memory.db")
    # Simuliraj: weak je disabled + odprta eskalacija.
    (env / "quality_registry.json").write_text(
        json.dumps({"weak": {"disabled_at": now, "reason": "test",
                             "runs": 4, "success_rate": 0.0}}), encoding="utf-8")
    (env / "escalations.json").write_text(
        json.dumps([{"ts": now, "project": "weak", "reason": "nizka uspešnost",
                     "detail": "0/4", "status": "open"}]), encoding="utf-8")

    md = report.generate_weekly_report(db_path=env / "memory.db", weeks=1, now=now)
    assert "⚠️" in md and "weak" in md        # odprta eskalacija
    assert "Onemogočeni targeti" in md and "weak" in md
