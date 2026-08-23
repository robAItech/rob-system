"""tests/test_meta_eval.py — Zanka 4: meta-evalvacija samorazvoja.

C3 — metrike berejo run_reviews (čista tabela), NIKOLI task_history (onesnažen
s test_proj vrsticami). Preveri merjenje, snapshot/primejavo, verzijski gate
in avtomatski rollback ob regresiji. Deterministično, brez LLM-a.
"""

import json

from core.meta_eval import METRIC_VERSION, MetaEvaluator
from core.run_review import RunReviewer


def _seed(db, n_green: int, n_failed: int):
    """Seed poštenih metrik neposredno v run_reviews (kot pravi orkestrator)."""
    r = RunReviewer(db)
    for i in range(n_green):
        r._insert_review({"project": f"green{i}", "directive": "x", "outcome": "green"},
                         "correct", "ok")
    for i in range(n_failed):
        r._insert_review({"project": f"fail{i}", "directive": "x", "outcome": "failed"},
                         "recurring_error", "napaka")


def test_metrics_computes_success_rate(tmp_path):
    db = tmp_path / "memory.db"
    _seed(db, 1, 1)

    m = MetaEvaluator(db).metrics()
    assert m["runs"] == 2
    assert m["green"] == 1
    assert m["success_rate"] == 0.5
    assert m["metric_version"] == METRIC_VERSION


def test_metrics_ignores_task_history(tmp_path):
    """C3 — task_history (test_proj onesnažen) se NE šteje več v uspešnost."""
    from core.gbrain_bridge import GBrainBridge
    db = tmp_path / "memory.db"
    # 10 zelenih v task_history (onesnaženje) + 1 green/1 failed v run_reviews.
    gb = GBrainBridge(db)
    for i in range(10):
        gb.record_task(f"test_proj{i}", "x", "VERIFIED GREEN", verified_code="Pass")
    _seed(db, 1, 1)

    m = MetaEvaluator(db).metrics()
    assert m["runs"] == 2      # samo run_reviews
    assert m["green"] == 1
    assert m["success_rate"] == 0.5


def test_compare_no_regression_when_unchanged(tmp_path):
    db = tmp_path / "memory.db"
    _seed(db, 10, 0)

    e = MetaEvaluator(db)
    sid = e.snapshot("baseline")
    res = e.compare(sid)
    assert res["regressed"] is False
    assert res["success_delta"] == 0.0


def test_compare_detects_regression(tmp_path):
    db = tmp_path / "memory.db"
    _seed(db, 10, 0)

    e = MetaEvaluator(db)
    sid = e.snapshot("baseline")
    _seed(db, 0, 10)  # uspešnost pade s 100% na 50%

    res = e.compare(sid)
    assert res["regressed"] is True
    assert res["success_delta"] < -0.05


def test_check_rolls_back_on_regression(tmp_path):
    db = tmp_path / "memory.db"
    _seed(db, 10, 0)

    e = MetaEvaluator(db)
    sid = e.snapshot("baseline")
    _seed(db, 0, 10)

    res = e.check(sid)
    assert res["regressed"] is True
    assert "rolled_back" in res


def test_compare_missing_snapshot(tmp_path):
    e = MetaEvaluator(tmp_path / "memory.db")
    res = e.compare(999)
    assert res["regressed"] is False
    assert "error" in res


def test_snapshot_includes_metric_version(tmp_path):
    db = tmp_path / "memory.db"
    _seed(db, 1, 0)
    e = MetaEvaluator(db)
    sid = e.snapshot("v2")
    snap = e.get_snapshot(sid)
    assert snap["metrics"]["metric_version"] == METRIC_VERSION


def test_compare_incomparable_stari_v1_vs_novi_v2(tmp_path):
    """C3 — stari v1 snapshot (task_history, brez metric_version) ≠ nov v2 → incomparable."""
    db = tmp_path / "memory.db"
    _seed(db, 1, 0)
    e = MetaEvaluator(db)
    # Ročno vstavi star v1 snapshot brez metric_version.
    with e._get_connection() as conn:
        conn.execute(
            "INSERT INTO meta_snapshots (label, metrics) VALUES (?, ?)",
            ("stari-v1", json.dumps({"runs": 56, "green": 46, "success_rate": 0.82})),
        )
        old_id = conn.execute("SELECT MAX(id) AS id FROM meta_snapshots").fetchone()["id"]

    res = e.compare(old_id)
    assert res["regressed"] is False
    assert res["incomparable"] is True
    # check() ne sme sprožiti rollbacka na neprimerljivi snapshot.
    res_check = e.check(old_id)
    assert res_check["regressed"] is False
    assert "rolled_back" not in res_check
