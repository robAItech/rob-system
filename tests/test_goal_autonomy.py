"""tests/test_goal_autonomy.py — Zanka 10: avtonomija ciljev."""

import pytest

from core.gbrain_bridge import GBrainBridge
from core.goal_autonomy import GoalProposer


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    from core.run_review import RunReviewer
    monkeypatch.setattr(RunReviewer, "_llm_available", staticmethod(lambda: False))


def _seed_review(db, cause: str):
    from core.run_review import RunReviewer
    RunReviewer(db).review({"project": "p", "directive": "d", "outcome": "failed",
                            "traceback": "ista napaka ValueError po 3 poskusih", "llm_calls": 2})


def test_analyze_finds_weak_projects(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    for _ in range(5):
        gb.record_task("p", "x", "FAILED", traceback="err")

    a = GoalProposer(db).analyze()
    assert len(a["weak_projects"]) == 1
    assert a["weak_projects"][0]["project"] == "p"
    assert a["weak_projects"][0]["fail_rate"] == 1.0


def test_propose_suggests_tune_on_recurring(tmp_path):
    db = tmp_path / "memory.db"
    _seed_review(db, "recurring_error")
    _seed_review(db, "recurring_error")

    goals = GoalProposer(db).propose()
    assert any(g["action"] == "tune" for g in goals)


def test_propose_suggests_consolidate_on_pitfalls(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    for i in range(3):
        gb.add_blacklist_pattern("p", f"E{i}", "mit")

    goals = GoalProposer(db).propose()
    assert any(g["action"] == "consolidate" for g in goals)


def test_propose_empty_no_signal(tmp_path):
    assert GoalProposer(tmp_path / "memory.db").propose() == []


def test_run_cycle_dry_run_only_proposes(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    for _ in range(5):
        gb.record_task("p", "x", "FAILED", traceback="err")

    res = GoalProposer(db).run_cycle(dry_run=True)
    assert "proposed" in res
    assert "dispatched" not in res
