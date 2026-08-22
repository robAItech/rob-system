"""Testi za P2 — plan-time kontekst (core/plan_context.py). Brez omrežja, brez LLM."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings
from core.memory_consolidation import MemoryConsolidator
from core.plan_context import build_plan_context, prepend_context, strip_plan_context
from core.run_review import RunReviewer


def test_build_plan_context_brez_lekcij_vsebuje_samo_napoved(tmp_path):
    """Prazna baza → samo svetovni model (napoved), ne lekcije."""
    ctx = build_plan_context(tmp_path / "memory.db", project="p", goal="zgradi API")
    assert "NAPOVED SVETOVNEGA MODELA" in ctx
    assert "PREJŠNJE LEKCIJE" not in ctx
    assert "ZADNJI TEKI" not in ctx


def test_build_plan_context_vkljuci_lekcije_in_napoved(tmp_path):
    """Zasejane lekcije + review → kontekst vsebuje vse sekcije."""
    db = tmp_path / "memory.db"
    RunReviewer(db).review({"project": "p", "directive": "zgradi API", "goal": "zgradi API",
                            "outcome": "failed", "traceback": "ista napaka ValueError po 3 poskusih"})
    MemoryConsolidator(db).store("demo: NameError", "NameError se zgodi, ko ime ni definirano.",
                                 project="p", kind="pitfall")
    ctx = build_plan_context(db, project="p", goal="NameError API")
    assert "ZADNJI TEKI" in ctx
    assert "PREJŠNJE LEKCIJE" in ctx
    assert "NAPOVED SVETOVNEGA MODELA" in ctx


def test_strip_plan_context_odstrani_markerje():
    assert strip_plan_context("[PLAN KONTEKST]\nfoo\n=== KONIEC KONTEKSTA ===\nCilj: x") == "Cilj: x"
    assert strip_plan_context("Cilj: x") == "Cilj: x"


def test_prepend_context_doda_markerje():
    out = prepend_context("Cilj: x", "lekcija")
    assert out.startswith("[PLAN KONTEKST]")
    assert "=== KONIEC KONTEKSTA ===" in out
    assert out.endswith("Cilj: x")
    assert prepend_context("Cilj: x", "") == "Cilj: x"


def test_build_plan_context_off_z_config(tmp_path, monkeypatch):
    """LLM_PLAN_CONTEXT=false → kontekst je prazen (off-switch)."""
    monkeypatch.setattr(settings, "llm_plan_context", False)
    assert build_plan_context(tmp_path / "memory.db", project="p", goal="x") == ""
