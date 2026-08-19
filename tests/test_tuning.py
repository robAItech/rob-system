"""tests/test_tuning.py — Zanka 3 (globlje): samorazvojni parametri orkestracije.

Preveri verzioniran Tuning register (meje + rollback) in cikel samorazvojnega
uglaševanja (tune_cycle). Testi ne kličejo LLM-a — predlog se mock-a.
"""

import pytest

from core.self_improve import SelfImprover
from core.tuning import Tuning


def test_tuning_get_default(tmp_path):
    t = Tuning(tmp_path / "memory.db")
    assert t.get("max_attempts") == 5
    assert t.get("repeat_abort_after") == 3


def test_tuning_set_promote_rollback(tmp_path):
    t = Tuning(tmp_path / "memory.db")

    v1 = t.set("max_attempts", 7)
    t.promote("max_attempts", v1)
    assert t.get("max_attempts") == 7

    v2 = t.set("max_attempts", 9)
    t.promote("max_attempts", v2)
    assert t.get("max_attempts") == 9

    # Rollback vrne na prejšnjo aktivno vrednost (7).
    assert t.rollback("max_attempts") == v1
    assert t.get("max_attempts") == 7


def test_tuning_bounds_reject(tmp_path):
    t = Tuning(tmp_path / "memory.db")
    with pytest.raises(ValueError):
        t.set("max_attempts", 100)  # izven mej (1..10)


def test_tune_cycle_promotes_in_bounds(tmp_path, monkeypatch):
    imp = SelfImprover(tmp_path / "memory.db")
    monkeypatch.setattr(imp, "propose_tuning", lambda current, context: {"max_attempts": 4})
    monkeypatch.setattr(imp, "evaluate", lambda test_targets=None: True)

    res = imp.tune_cycle(context="")
    assert res["promoted"] is True
    assert Tuning(tmp_path / "memory.db").get("max_attempts") == 4


def test_tune_cycle_rejects_out_of_bounds(tmp_path, monkeypatch):
    imp = SelfImprover(tmp_path / "memory.db")
    monkeypatch.setattr(imp, "propose_tuning", lambda current, context: {"max_attempts": 99})

    res = imp.tune_cycle(context="")
    assert res["promoted"] is False
    assert res["reason"].startswith("guard")
    assert Tuning(tmp_path / "memory.db").get("max_attempts") == 5  # nespremenjeno
