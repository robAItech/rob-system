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


def test_propose_scores_with_learning_value(tmp_path):
    """P4 — novost (manj poskusov) → višja učna vrednost → prehiti izkušenejši projekt."""
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    for _ in range(20):
        gb.record_task("old", "x", "FAILED", traceback="err")     # izkušen, nizka novost
    for _ in range(3):
        gb.record_task("fresh", "x", "FAILED", traceback="err")   # svež, visoka novost

    goals = GoalProposer(db).propose()
    projects = [g["project"] for g in goals if g["action"] == "build"]
    assert projects.index("fresh") < projects.index("old")


def test_propose_prefer_learn_vs_success(tmp_path):
    """P4 — --prefer spremeni top nalogo (kodira zaklenjene konstante)."""
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    for _ in range(5):
        gb.record_task("p", "x", "FAILED", traceback="err")       # weak
    for _ in range(10):
        gb.record_task("other", "x", "VERIFIED GREEN", verified_code="Pass")  # global ≈0.67
    _seed_review(db, "recurring_error")
    _seed_review(db, "recurring_error")

    gp = GoalProposer(db)
    assert gp.propose(prefer="success")[0]["action"] == "tune"    # izvedljivost
    assert gp.propose(prefer="learn")[0]["action"] == "build"     # učenje


def test_propose_includes_predicted_success(tmp_path):
    """P4 — vsak goal ima predicted_success / learning_value / score v [0,1]."""
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    for _ in range(5):
        gb.record_task("p", "x", "FAILED", traceback="err")
    _seed_review(db, "recurring_error")
    _seed_review(db, "recurring_error")
    for i in range(3):
        gb.add_blacklist_pattern("p", f"E{i}", "mit")

    goals = GoalProposer(db).propose(limit=5)
    assert goals
    for g in goals:
        assert "predicted_success" in g and "learning_value" in g and "score" in g
        assert 0.0 <= g["predicted_success"] <= 1.0
        assert 0.0 <= g["learning_value"] <= 1.0
        assert 0.0 <= g["score"] <= 1.0
