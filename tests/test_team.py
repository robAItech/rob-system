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
    # Executor "zgradi" (vrne True), ampak verify pade (ni realnega modula) →
    # retry zanka poskusi do 3×, nato built=False.
    res = tc.run("demo", "zgradi x",
                 executor=lambda g: (seen.append(g) or True), max_attempts=3)
    assert res["built"] is False
    assert res["attempts"] == 3
    assert res["retried"] is True
    assert len(seen) == 3            # 3 poskusi
    assert seen[0] == "zgradi x"     # prvi poskus = prvotni cilj


def test_run_retries_until_verify_passes(monkeypatch):
    """Retry zanka: verify pade 1×, nato uspe → 2 poskusa, built True."""
    tc = TeamCoordinator()
    calls = {"exec": 0}

    def fake_executor(g):
        calls["exec"] += 1
        return True

    verdicts = iter([{"ok": False, "reason": "Reality check: healthy napaka"},
                     {"ok": True, "reason": "ok"}])
    monkeypatch.setattr(tc, "verify", lambda *a, **k: next(verdicts))
    res = tc.run("demo", "zgradi x", executor=fake_executor, max_attempts=3)
    assert res["built"] is True
    assert res["attempts"] == 2
    assert res["retried"] is True
    assert calls["exec"] == 2


def test_run_revises_on_high_severity(monkeypatch):
    tc = TeamCoordinator()
    monkeypatch.setattr(tc, "critique", lambda goal, plan, context=None: {"severity": "high", "objections": ["luknja v načrtu"]})
    res = tc.run("demo", "zgradi x", executor=lambda g: True)
    assert res["revised"] is True
    assert res["severity"] == "high"


def test_run_reports_build_failure():
    tc = TeamCoordinator()
    res = tc.run("demo", "zgradi x", executor=lambda g: False)
    assert res["built"] is False
