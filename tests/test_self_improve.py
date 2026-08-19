"""tests/test_self_improve.py — Zanka 3: samorazvoj orkestracije (RSI nase).

Preveri register promptov (verzioniranje + rollback) in samorazvojni cikel
(guard invariante + promocija/zavrnitev). Testi ne kličejo LLM-a — predlog in
regresijska vrata se mock-ajo.
"""

from core.prompt_registry import PromptRegistry
from core.self_improve import PROMPT_NAME, SelfImprover


def test_registry_propose_promote_rollback(tmp_path):
    r = PromptRegistry(tmp_path / "memory.db")

    # Pred prvo promocijo ni aktivne verzije → fallback na privzeto.
    assert r.get_active("x", "default") == "default"

    v1 = r.propose("x", "vsebina v1")
    v2 = r.propose("x", "vsebina v2")
    assert r.get_active("x", "default") == "default"  # predloga še nista aktivna

    r.promote("x", v1)
    assert r.get_active("x") == "vsebina v1"

    r.promote("x", v2)
    assert r.get_active("x") == "vsebina v2"

    # Rollback vrne na prejšnjo aktivno verzijo (v1).
    assert r.rollback("x") == v1
    assert r.get_active("x") == "vsebina v1"

    hist = r.history("x")
    assert len(hist) == 2
    assert {h["status"] for h in hist} >= {"active", "superseded"}


def test_registry_rollback_without_previous_is_none(tmp_path):
    r = PromptRegistry(tmp_path / "memory.db")
    assert r.rollback("x") is None  # ni ničesar za rollback


def test_guard_retains_invariants(tmp_path):
    imp = SelfImprover(tmp_path / "memory.db")

    ok = imp.guard(PROMPT_NAME, "### FILE: format\ntest datotek se ne spreminja\ncilj 100% zelen")
    assert ok["ok"] is True

    bad = imp.guard(PROMPT_NAME, "nek splošen prompt brez varnostnih zahtev")
    assert bad["ok"] is False
    assert "### FILE:" in bad["missing"]


def test_run_cycle_promotes_on_green(tmp_path, monkeypatch):
    imp = SelfImprover(tmp_path / "memory.db")
    candidate = "### FILE: x\ntestni guard\n100% zelen nov prompt"

    def fake_propose(name, current, context):
        vid = imp.registry.propose(name, candidate, note="test")
        return {"version_id": vid, "content": candidate}

    monkeypatch.setattr(imp, "propose", fake_propose)
    monkeypatch.setattr(imp, "evaluate", lambda test_targets=None: True)

    res = imp.run_cycle("trenutni prompt", context="")
    assert res["promoted"] is True
    assert imp.registry.get_active(PROMPT_NAME) == candidate


def test_run_cycle_rejects_on_guard_failure(tmp_path, monkeypatch):
    imp = SelfImprover(tmp_path / "memory.db")

    def fake_propose(name, current, context):
        vid = imp.registry.propose(name, "brez invariant", note="test")
        return {"version_id": vid, "content": "brez invariant"}

    monkeypatch.setattr(imp, "propose", fake_propose)

    res = imp.run_cycle("trenutni prompt")
    assert res["promoted"] is False
    assert res["reason"].startswith("guard")

    hist = imp.registry.history(PROMPT_NAME)
    assert hist[0]["status"] == "rejected"


def test_run_cycle_no_proposal(tmp_path, monkeypatch):
    imp = SelfImprover(tmp_path / "memory.db")
    monkeypatch.setattr(imp, "propose", lambda name, current, context: None)

    res = imp.run_cycle("trenutni prompt")
    assert res["proposed"] is False
