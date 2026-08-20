"""tests/test_rlaif.py — Zanka 9: učenje preferenc (RLAIF)."""

from core.gbrain_bridge import GBrainBridge
from core.rlaif import PreferenceCollector


def test_collect_pairs_empty(tmp_path):
    assert PreferenceCollector(tmp_path / "memory.db").collect_pairs() == []


def test_collect_pairs_matches_green_with_failed(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    gb.record_task("p", "dober pristop", "VERIFIED GREEN", verified_code="Pass")
    gb.record_task("p", "slab pristop", "FAILED", traceback="err")

    pairs = PreferenceCollector(db).collect_pairs()
    assert len(pairs) == 1
    assert pairs[0]["chosen"] == "dober pristop"
    assert pairs[0]["rejected"] == "slab pristop"


def test_collect_pairs_skips_green_only(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    gb.record_task("p", "dober", "VERIFIED GREEN", verified_code="Pass")
    assert PreferenceCollector(db).collect_pairs() == []


def test_export_writes_jsonl(tmp_path):
    db = tmp_path / "memory.db"
    gb = GBrainBridge(db)
    gb.record_task("p", "dober", "VERIFIED GREEN", verified_code="Pass")
    gb.record_task("p", "slab", "FAILED", traceback="err")

    path = tmp_path / "prefs.jsonl"
    n = PreferenceCollector(db).export(str(path))
    assert n == 1
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    assert '"chosen": "dober"' in lines[0]
