"""tests/test_team.py — Zanka 6: multi-agent adversarial koordinacija.

Preveri vloge (planner/critic/verifier) in cel adversarial cikel (plan →
critique → revise → build → verify). Testi prisilijo hevristični fallback
(brez LLM) in mock-ajo executor.
"""

import pytest

from core.team import TeamCoordinator


@pytest.fixture(autouse=True)
def _force_heuristic(monkeypatch):
    monkeypatch.setattr(TeamCoordinator, "_llm_available", staticmethod(lambda: False))


def test_plan_heuristic_returns_goal():
    assert TeamCoordinator().plan("zgradi x") == "zgradi x"


def test_critique_heuristic_low():
    c = TeamCoordinator().critique("zgradi x", "načrt")
    assert c["severity"] == "low"
    assert c["objections"] == []


def test_run_flow_with_mock_executor():
    tc = TeamCoordinator()
    seen = []
    res = tc.run("demo", "zgradi x", executor=lambda g: (seen.append(g) or True))
    assert res["built"] is True
    assert res["revised"] is False  # low → ni revizije
    assert res["severity"] == "low"
    assert seen == ["zgradi x"]


def test_run_revises_on_high_severity(monkeypatch):
    tc = TeamCoordinator()
    monkeypatch.setattr(tc, "critique", lambda goal, plan: {"severity": "high", "objections": ["luknja v načrtu"]})
    res = tc.run("demo", "zgradi x", executor=lambda g: True)
    assert res["revised"] is True
    assert res["severity"] == "high"


def test_run_reports_build_failure():
    tc = TeamCoordinator()
    res = tc.run("demo", "zgradi x", executor=lambda g: False)
    assert res["built"] is False
