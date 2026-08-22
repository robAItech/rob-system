"""Enotni smoke testi za P5 eval (evaluate_autonomy.py) — BREZ LLM/RSI/Docker.

Preverijo, da je eval struktura (EVAL_CASES, smoke_check) veljavna in stabilna,
ne da bi izvajali avtonomno zanko (ki bi klic a DeepSeek/Docker). Izvedbeno
eval razširjenega stanja se izvrši namensko prek `python evaluate_autonomy.py`
ali `./rob eval`, NE kot del zagona `pytest tests/`.
"""
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluate_autonomy import EVAL_CASES, AutonomyEval, validate_case
from unittest import mock


def test_eval_cases_so_dobro_oblikovani():
    """Vsak case ima veljaven name/direktivo in polja veljavna za svoj 'type'."""
    assert len(EVAL_CASES) >= 2, "potrebujemo vsaj 2 reprezentativna case-a"
    assert len({c.get("type", "function") for c in EVAL_CASES}) >= 2, \
        "lestvica naj pokrije vsaj 2 tipa (npr. function + pydantic/http)"
    for c in EVAL_CASES:
        errs = validate_case(c)
        assert not errs, f"{c['name']}: {errs}"


def test_smoke_check_veljaven():
    evaluator = AutonomyEval(EVAL_CASES)
    assert all(evaluator.smoke_check(c) for c in EVAL_CASES)


def test_run_case_manjkajoca_funkcija_ne_crash(tmp_path, monkeypatch):
    """`run_case` ob RSI-zelen, a manjkajoči funkciji vrne checks 0, ne crash.

    Preverimo, da eval robustno obravnava primer, ko je RSI zelen (pytest v
    sandboxu) a eval ne najde funkcije v kloniranem modulu → prijavi, ne pade.
    """
    from unittest import mock
    evaluator = AutonomyEval([EVAL_CASES[0]])
    # RSI "gre skozi": patch tam, kjer ga run_case import-ira (core.orchestrator).
    with mock.patch("core.orchestrator.RobAIOrchestrator.run", return_value=True), \
         mock.patch.object(AutonomyEval, "_load_checkable_func", return_value=None):
        res = evaluator.run_case(EVAL_CASES[0])
    assert res["rsi_ok"] is True
    assert res["checks_ok"] == 0
    assert "ni najdena" in res["reason"]


def test_run_all_vzporedno_ohranja_vrstni_red():
    """Korak 7 — run_all(workers=2) zbira rezultate v vrstnem redu case-ov."""
    cases = [EVAL_CASES[0], EVAL_CASES[1]]
    ev = AutonomyEval(cases)

    def fake(case):
        return {"name": case["name"], "rsi_ok": True, "checks_ok": 1,
                "checks_total": 1, "reason": "ok", "wall_seconds": 1.0}

    with mock.patch.object(ev, "run_case", side_effect=fake):
        s = ev.run_all(workers=2)
    assert [r["name"] for r in ev.results] == [c["name"] for c in cases]
    assert s == {"passed": 2, "total": 2, "rate": 1.0}


def test_run_all_izjema_enega_ne_zruši():
    """Korak 7 — padec enega case-a ne zruši run_all; ostali uspejo."""
    cases = [EVAL_CASES[0], EVAL_CASES[1]]
    ev = AutonomyEval(cases)

    def fake(case):
        if case["name"] == "divide_safe":
            raise RuntimeError("boom")
        return {"name": case["name"], "rsi_ok": True, "checks_ok": 1,
                "checks_total": 1, "reason": "ok", "wall_seconds": 1.0}

    with mock.patch.object(ev, "run_case", side_effect=fake):
        s = ev.run_all(workers=2)
    assert len(ev.results) == 2
    assert ev.results[1]["rsi_ok"] is False and "padel" in ev.results[1]["reason"]
    assert s == {"passed": 1, "total": 2, "rate": 0.5}
