"""tests/test_world_model.py — Zanka 7: svetovni model (napoved izidov)."""

import pytest

from core.gbrain_bridge import GBrainBridge
from core.world_model import WorldModel


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    from core.run_review import RunReviewer
    monkeypatch.setattr(RunReviewer, "_llm_available", staticmethod(lambda: False))


def _seed_tasks(gb: GBrainBridge, project: str, n_green: int, n_failed: int):
    for _ in range(n_green):
        gb.record_task(project, "x", "VERIFIED GREEN", verified_code="Pass")
    for _ in range(n_failed):
        gb.record_task(project, "x", "FAILED", traceback="err")


def _seed_review(db, cause: str):
    from core.run_review import RunReviewer
    RunReviewer(db).review({"project": "p", "directive": "d", "outcome": "failed",
                            "traceback": "ista napaka ValueError po 3 poskusih", "llm_calls": 2})


def test_predict_uses_project_success_rate(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed_tasks(gb, "auth", 10, 0)
    p = WorldModel(db).predict("zgradi API", project="auth")
    assert p["success_prob"] >= 0.9


def test_predict_uses_global_fallback(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed_tasks(gb, "a", 8, 2)  # global 80%
    p = WorldModel(db).predict("zgradi x", project="nov_projekt")
    assert abs(p["success_prob"] - 0.8) < 0.01


def test_predict_pitfalls_lower_prob(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed_tasks(gb, "risk", 10, 0)  # 100% uspešnost
    for i in range(4):
        gb.add_blacklist_pattern("risk", f"Error{i}", "mit")
    p = WorldModel(db).predict("zgradi", project="risk")
    assert p["pitfalls"] == 4
    assert p["success_prob"] < 0.85  # 1.0 - 4*0.05 = 0.8


def test_predict_likely_cause(tmp_path):
    db = tmp_path / "memory.db"
    _seed_review(db, "recurring_error")
    p = WorldModel(db).predict("zgradi x")
    assert p["likely_cause"] == "recurring_error"


def test_predict_empty_data(tmp_path):
    p = WorldModel(tmp_path / "memory.db").predict("zgradi x")
    assert p["success_prob"] == 0.5


def test_best_returns_highest_prob(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed_tasks(gb, "good", 10, 0)
    goal, pred = WorldModel(db).best(["zgradi x", "zgradi y"], project="good")
    assert pred["success_prob"] >= 0.9
    assert goal in ("zgradi x", "zgradi y")
