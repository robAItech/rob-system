"""Testi za P7 — learning dashboard (core/learning_dashboard.py). Brez omrežja."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.learning_dashboard import render
from core.prompt_registry import PromptRegistry
from core.run_review import RunReviewer
from core.strategy_reflect import PRINCIPLES_PROMPT_NAME, StrategyReflector


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    monkeypatch.setattr(RunReviewer, "_llm_available", staticmethod(lambda: False))


def _seed(db):
    RunReviewer(db).review({"project": "p", "directive": "d", "outcome": "failed",
                            "traceback": "ista napaka ValueError po 3 poskusih"})
    RunReviewer(db).review({"project": "p", "directive": "d", "outcome": "green"})
    r = StrategyReflector(db)
    vid = r.store_principles(json.dumps([{"principle": "Preveri sheme", "rationale": "zato"}]))
    PromptRegistry(db).promote(PRINCIPLES_PROMPT_NAME, vid)


def test_render_contains_sections(tmp_path):
    db = tmp_path / "memory.db"
    _seed(db)
    hist = tmp_path / "eval_history.json"
    hist.write_text(json.dumps([
        {"date": "2026-08-18T00:00:00+00:00", "passed": 2, "total": 3, "rate": 0.667},
        {"date": "2026-08-18T01:00:00+00:00", "passed": 3, "total": 3, "rate": 1.0},
    ]), encoding="utf-8")

    out = render(db_path=db, eval_history_path=hist)
    for section in ("SISTEMSKE METRIKE", "EVAL TREND", "OPERATIVNA NAČELA",
                    "DOMINANTNI VZORCI", "ZADNJE LEKCIJE"):
        assert section in out
    assert "67%" in out or "100%" in out   # eval trend


def test_render_does_not_crash_empty(tmp_path):
    out = render(db_path=tmp_path / "x.db", eval_history_path=tmp_path / "none.json")
    assert isinstance(out, str)
    assert "SISTEMSKE METRIKE" in out
