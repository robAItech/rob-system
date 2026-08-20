"""tests/test_fork.py — Zanka 8: paralelno raziskovanje (fork)."""

import pytest

from core.fork import Explorer
from core.gbrain_bridge import GBrainBridge


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setattr(Explorer, "_llm_available", staticmethod(lambda: False))


def _seed_tasks(gb: GBrainBridge, project: str, n_green: int, n_failed: int):
    for _ in range(n_green):
        gb.record_task(project, "x", "VERIFIED GREEN", verified_code="Pass")
    for _ in range(n_failed):
        gb.record_task(project, "x", "FAILED", traceback="err")


def test_propose_variants_heuristic():
    assert Explorer().propose_variants("zgradi x", n=3) == ["zgradi x"]


def test_explore_ranks_by_severity(tmp_path, monkeypatch):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed_tasks(gb, "p", 10, 0)  # 100% uspešnost

    ex = Explorer(db)
    monkeypatch.setattr(ex, "propose_variants", lambda goal, n: ["a", "b", "c"])
    monkeypatch.setattr(ex, "_critique", lambda goal, v: {"severity": "high" if v == "b" else "low", "objections": []})

    res = ex.explore("goal", n=3, project="p")
    assert res["best"]["variant"] == "a"
    assert res["ranked"][0]["variant"] == "a"
    assert res["ranked"][-1]["variant"] == "b"  # "b" kaznovan (high severity)


def test_explore_and_run_executes_best(tmp_path, monkeypatch):
    db = tmp_path / "memory.db"
    ex = Explorer(db)
    monkeypatch.setattr(ex, "propose_variants", lambda goal, n: ["prvi", "drugi"])
    monkeypatch.setattr(ex, "_critique", lambda goal, v: {"severity": "low", "objections": []})

    seen = []
    res = ex.explore_and_run("goal", n=2, project="p", executor=lambda g: (seen.append(g) or True))
    assert res["executed"] is True
    assert seen == ["prvi"]  # najboljši (prvi) se izvede
