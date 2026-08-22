"""Testi za P5 — prečni vzorci neuspehov (core/pattern_detect.py). Brez omrežja."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pattern_detect import PatternDetector
from core.run_review import NEXT_STEP, RunReviewer


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setattr(RunReviewer, "_llm_available", staticmethod(lambda: False))


def _seed_review(db, project: str):
    RunReviewer(db).review({"project": project, "directive": "d", "outcome": "failed",
                            "traceback": "ista napaka ValueError po 3 poskusih", "llm_calls": 2})


def test_detect_cross_project_pattern(tmp_path):
    db = tmp_path / "memory.db"
    for proj in ("billing", "payments", "demo"):
        _seed_review(db, proj)
    patterns = PatternDetector(db).detect_cross_task_patterns()
    rec = next((p for p in patterns if p["cause"] == "recurring_error"), None)
    assert rec is not None
    assert rec["projects"] == 3
    assert rec["total"] == 3
    assert rec["share"] == 1.0


def test_recommendation_from_next_step(tmp_path):
    db = tmp_path / "memory.db"
    for proj in ("billing", "payments", "demo"):
        _seed_review(db, proj)
    patterns = PatternDetector(db).detect_cross_task_patterns()
    assert patterns[0]["recommendation"] == NEXT_STEP["recurring_error"]["hint"]


def test_dominant_pattern(tmp_path):
    db = tmp_path / "memory.db"
    for proj in ("billing", "payments", "demo"):
        _seed_review(db, proj)
    patterns = PatternDetector(db).detect_cross_task_patterns()
    assert PatternDetector.dominant_pattern(patterns) is patterns[0]
    assert PatternDetector.dominant_pattern([]) is None


def test_min_thresholds(tmp_path):
    db = tmp_path / "memory.db"
    _seed_review(db, "only")
    _seed_review(db, "only")
    assert PatternDetector(db).detect_cross_task_patterns(min_projects=2) == []


def test_empty_db(tmp_path):
    assert PatternDetector(tmp_path / "memory.db").detect_cross_task_patterns() == []
