"""Unit testi za core/quality.py (kvalitetni prag + eskalacija) in integracija
z goal_autonomy (preskoči disabled targete). Brez pravih zunanjih klicev —
DB in registri so usmerjeni v tmp_path."""

import json
import sqlite3

import pytest

from core import audit, goal_autonomy, quality


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Usmeri DB, registra in audit log v tmp_path."""
    monkeypatch.setattr(quality, "DEFAULT_DB", tmp_path / "memory.db")
    monkeypatch.setattr(quality, "QUALITY_REGISTRY", tmp_path / "quality_registry.json")
    monkeypatch.setattr(quality, "ESCALATIONS_FILE", tmp_path / "escalations.json")
    monkeypatch.setattr(audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    return tmp_path


def _make_db(path, rows):
    """Ustvari memory.db z run_reviews vrsticami (project, outcome)."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS run_reviews ("
                 "id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, "
                 "directive TEXT NOT NULL, outcome TEXT NOT NULL, "
                 "root_cause TEXT NOT NULL, lesson TEXT)")
    for project, outcome in rows:
        conn.execute("INSERT INTO run_reviews (project, directive, outcome, root_cause) "
                     "VALUES (?, 'x', ?, 'unknown')", (project, outcome))
    conn.commit()
    conn.close()


def _write_audit(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ #
#  project_quality
# ------------------------------------------------------------------ #
def test_project_quality_missing_db_ok(env):
    assert quality.project_quality(env / "ni.db") == {}


def test_project_quality_counts(env):
    db = env / "memory.db"
    _make_db(db, [("a", "green"), ("a", "failed"), ("a", "green"), ("b", "failed")])
    q = quality.project_quality(db)
    assert q["a"]["runs"] == 3 and q["a"]["green"] == 2 and q["a"]["failed"] == 1
    assert q["a"]["success_rate"] == round(2 / 3, 4)
    assert q["b"]["runs"] == 1 and q["b"]["success_rate"] == 0.0


# ------------------------------------------------------------------ #
#  run_gate
# ------------------------------------------------------------------ #
def test_run_gate_flags_low_quality_and_escalates(env):
    db = env / "memory.db"
    _make_db(db, [("weak", "failed")] * 4 + [("good", "green")] * 5)
    res = quality.run_gate(min_runs=3, min_success_rate=0.5, db_path=db)
    assert res["checked"] >= 2 and res["flagged"] == 1 and res["escalated"] == 1
    assert quality.is_disabled("weak")
    assert not quality.is_disabled("good")
    esc = quality.open_escalations()
    assert len(esc) == 1 and esc[0]["project"] == "weak" and esc[0]["status"] == "open"


def test_run_gate_idempotent(env):
    db = env / "memory.db"
    _make_db(db, [("weak", "failed")] * 4)
    quality.run_gate(min_runs=3, min_success_rate=0.5, db_path=db)
    res2 = quality.run_gate(min_runs=3, min_success_rate=0.5, db_path=db)
    # Drugi klic ne doda nove eskalacije (že odprta) in ne ponovi flag-a.
    assert res2["escalated"] == 0 and res2["flagged"] == 0
    assert len(quality.open_escalations()) == 1


def test_run_gate_escalation_writes_audit_event(env):
    db = env / "memory.db"
    _make_db(db, [("weak", "failed")] * 4)
    quality.run_gate(min_runs=3, min_success_rate=0.5, db_path=db)
    evs = audit.query(event="escalation")
    assert len(evs) == 1 and evs[0]["project"] == "weak" and evs[0]["status"] == "critical"


# ------------------------------------------------------------------ #
#  Disabled register / re-enable
# ------------------------------------------------------------------ #
def test_reenable_removes_disabled(env):
    db = env / "memory.db"
    _make_db(db, [("weak", "failed")] * 4)
    quality.run_gate(min_runs=3, min_success_rate=0.5, db_path=db)
    assert quality.is_disabled("weak")
    assert quality.reenable("weak")
    assert not quality.is_disabled("weak")
    assert not quality.reenable("weak")


def test_resolve_escalation(env):
    db = env / "memory.db"
    _make_db(db, [("weak", "failed")] * 4)
    quality.run_gate(min_runs=3, min_success_rate=0.5, db_path=db)
    assert quality.resolve_escalation("weak")
    assert quality.open_escalations() == []
    assert not quality.resolve_escalation("weak")


# ------------------------------------------------------------------ #
#  consecutive_fails (iz audit.jsonl)
# ------------------------------------------------------------------ #
def test_consecutive_fails_trailing(env):
    now = 1_000_000
    _write_audit(env / "audit.jsonl", [
        {"ts": now - 100, "event": "daemon-task", "project": "a", "status": "ok"},
        {"ts": now - 90, "event": "daemon-task", "project": "a", "status": "failed"},
        {"ts": now - 80, "event": "daemon-task", "project": "a", "status": "failed"},
        {"ts": now - 70, "event": "fleet-result", "project": "a", "status": "failed"},
        {"ts": now - 60, "event": "daemon-task", "project": "b", "status": "failed"},
    ])
    assert quality.consecutive_fails("a") == 3   # ok→failed×3 (trailing)
    assert quality.consecutive_fails("b") == 1


# ------------------------------------------------------------------ #
#  goal_autonomy — preskoči disabled targete
# ------------------------------------------------------------------ #
def _make_task_history(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS task_history ("
                 "task_id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, "
                 "prompt TEXT NOT NULL, status TEXT NOT NULL, "
                 "traceback TEXT, verified_code TEXT, timestamp TEXT)")
    for project, status in rows:
        conn.execute("INSERT INTO task_history (project, prompt, status) VALUES (?, 'p', ?)",
                     (project, status))
    conn.commit()
    conn.close()


def test_goal_autonomy_skips_disabled_target(env, monkeypatch):
    db = env / "memory.db"
    _make_task_history(db, [("weak", "FAILED")] * 4)   # _weak_projects jo pobere
    # Brez registra → weak je predlagana.
    gp = goal_autonomy.GoalProposer(db)
    goals_before = gp.propose(limit=10)
    assert any("weak" in g.get("goal", "") for g in goals_before)

    # Z registrom (disabled) → weak izpade iz predlogov ("ugasni agenta").
    import json as _json
    (env / "quality_registry.json").write_text(
        _json.dumps({"weak": {"disabled_at": 1, "reason": "test", "runs": 4,
                              "success_rate": 0.0}}), encoding="utf-8")
    goals_after = gp.propose(limit=10)
    assert not any("weak" in g.get("goal", "") for g in goals_after)
