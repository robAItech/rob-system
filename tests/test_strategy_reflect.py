"""Testi za P3 — strateška samorefleksija (core/strategy_reflect.py). Brez omrežja."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.prompt_registry import PromptRegistry
from core.strategy_reflect import PRINCIPLES_PROMPT_NAME, StrategyReflector
from core.run_review import RunReviewer


def _reflector(tmp_path):
    return StrategyReflector(tmp_path / "memory.db")


def test_guard_principles_struktura(tmp_path):
    r = _reflector(tmp_path)
    assert r.guard_principles([{"principle": "Preveri sheme", "rationale": "zato"}])["ok"]
    assert not r.guard_principles([])["ok"]
    assert not r.guard_principles([{"rationale": "brez principa"}])["ok"]
    assert not r.guard_principles([{"principle": "A"}, {"principle": "a"}])["ok"]   # duplikat


def test_guard_principles_noop_na_aktivnem(tmp_path):
    r = _reflector(tmp_path)
    content = json.dumps([{"principle": "X", "rationale": "Y"}])
    vid = r.store_principles(content)
    PromptRegistry(r.db_path).promote(PRINCIPLES_PROMPT_NAME, vid)
    assert not r.guard_principles(json.loads(content))["ok"]   # identičen aktivnemu


def test_format_principles(tmp_path):
    r = _reflector(tmp_path)
    out = r.format_principles(json.dumps([{"principle": "A", "rationale": "B"}]))
    assert "A" in out and "B" in out


def test_gather_lessons(tmp_path):
    r = _reflector(tmp_path)
    RunReviewer(tmp_path / "memory.db").review({
        "project": "p", "directive": "zgradi API", "goal": "zgradi API",
        "outcome": "failed", "traceback": "ista napaka ValueError po 3 poskusih",
    })
    lessons = r.gather_lessons(20)
    assert "p" in lessons
    assert "failed" in lessons or "recurring" in lessons


def test_run_cycle_promotes_on_green(tmp_path, monkeypatch):
    r = _reflector(tmp_path)
    monkeypatch.setattr(r, "propose_principles",
                        lambda lessons: [{"principle": "Preveri sheme", "rationale": "zato"}])
    monkeypatch.setattr(r, "evaluate", lambda test_targets=None: True)
    res = r.run_cycle()
    assert res["promoted"] is True
    assert "Preveri sheme" in r.current_principles()


def test_run_cycle_rejects_on_guard(tmp_path, monkeypatch):
    r = _reflector(tmp_path)
    monkeypatch.setattr(r, "propose_principles", lambda lessons: [{"rationale": "brez principa"}])
    res = r.run_cycle()
    assert res["promoted"] is False
    assert "guard" in res["reason"]


def test_run_cycle_no_proposal(tmp_path, monkeypatch):
    r = _reflector(tmp_path)
    monkeypatch.setattr(r, "propose_principles", lambda lessons: None)
    res = r.run_cycle()
    assert res["proposed"] is False
