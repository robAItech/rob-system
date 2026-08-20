"""tests/test_meta_eval.py — Zanka 4: meta-evalvacija samorazvoja.

Preveri merjenje uspešnosti, snapshot/primejavo in avtomatski rollback ob
regresiji. Testi so deterministični (brez LLM-a).
"""

from core.gbrain_bridge import GBrainBridge
from core.meta_eval import MetaEvaluator


def _seed(gb: GBrainBridge, n_green: int, n_failed: int):
    for i in range(n_green):
        gb.record_task(f"green{i}", "x", "VERIFIED GREEN", verified_code="Pass")
    for i in range(n_failed):
        gb.record_task(f"fail{i}", "x", "FAILED", traceback="err")


def test_metrics_computes_success_rate(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed(gb, 1, 1)

    m = MetaEvaluator(db).metrics()
    assert m["runs"] == 2
    assert m["green"] == 1
    assert m["success_rate"] == 0.5


def test_compare_no_regression_when_unchanged(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed(gb, 10, 0)

    e = MetaEvaluator(db)
    sid = e.snapshot("baseline")
    res = e.compare(sid)
    assert res["regressed"] is False
    assert res["success_delta"] == 0.0


def test_compare_detects_regression(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed(gb, 10, 0)

    e = MetaEvaluator(db)
    sid = e.snapshot("baseline")
    _seed(gb, 0, 10)  # uspešnost pade s 100% na 50%

    res = e.compare(sid)
    assert res["regressed"] is True
    assert res["success_delta"] < -0.05


def test_check_rolls_back_on_regression(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    _seed(gb, 10, 0)

    e = MetaEvaluator(db)
    sid = e.snapshot("baseline")
    _seed(gb, 0, 10)

    res = e.check(sid)
    assert res["regressed"] is True
    assert "rolled_back" in res


def test_compare_missing_snapshot(tmp_path):
    e = MetaEvaluator(tmp_path / "memory.db")
    res = e.compare(999)
    assert res["regressed"] is False
    assert "error" in res
