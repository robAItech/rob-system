"""tests/test_task_planner.py — Zanka 5: dekompozicija ciljev.

Testi prisilijo hevristično dekompozicijo (brez LLM/omrežja) in preverijo
razbijanje na podcilje ter izvedbo skozi executor.
"""

import pytest

from core.task_planner import TaskPlanner


@pytest.fixture(autouse=True)
def _force_heuristic(monkeypatch):
    monkeypatch.setattr(TaskPlanner, "_llm_available", staticmethod(lambda: False))


def test_decompose_heuristic_splits_on_semicolon():
    tp = TaskPlanner()
    steps = tp.decompose("zgradi UI; poveži API; napiši teste")
    assert steps == ["zgradi UI", "poveži API", "napiši teste"]


def test_decompose_heuristic_single_goal():
    tp = TaskPlanner()
    assert tp.decompose("zgradi eno stvar") == ["zgradi eno stvar"]


def test_execute_runs_all_steps():
    tp = TaskPlanner()
    seen = []
    res = tp.execute("a; b; c", executor=lambda s: (seen.append(s) or True))
    assert res["steps"] == 3
    assert res["completed"] == 3
    assert res["ok"] is True
    assert seen == ["a", "b", "c"]


def test_execute_reports_partial_failure():
    tp = TaskPlanner()
    res = tp.execute("a; b; c", executor=lambda s: s != "b")
    assert res["steps"] == 3
    assert res["completed"] == 2
    assert res["ok"] is False
