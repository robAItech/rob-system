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
