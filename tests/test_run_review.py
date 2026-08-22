"""tests/test_run_review.py — Zanka 2: post-run samoevalvacija odločitev.

Preveri: recenzent klasificira vzrok izida na nivoju odločitve, zapiše recenzijo
in (za konkretne neuspehe) vpiše lekcijo v semantični spomin (Zanka 1).
Testi prisilijo hevristično recenzijo (brez LLM/omrežja).
"""

import pytest

from core.run_review import RunReviewer


@pytest.fixture(autouse=True)
def _force_heuristic(monkeypatch):
    """Izklopi LLM recenzijo — testi tečejo lokalno, brez omrežja."""
    monkeypatch.setattr(RunReviewer, "_llm_available", staticmethod(lambda: False))


def test_review_failed_run_creates_review_and_lesson(tmp_path):
    r = RunReviewer(tmp_path / "memory.db")
    res = r.review({
        "project": "billing", "directive": "zgradi obračun DDV",
        "outcome": "failed", "traceback": "ista napaka ValueError po 3 poskusih",
        "llm_calls": 3, "attempts": 5, "spec_hint": "",
    })
    assert res["outcome"] == "failed"
    assert res["root_cause"] == "recurring_error"
    assert res["lesson"]  # konkretna lekcija

    stats = r.stats()
    assert stats["reviews"] == 1
    assert stats["by_cause"]["recurring_error"] == 1


def test_review_green_run_records_what_worked_and_lesson(tmp_path):
    """P1 — zeleni tek zdaj uči: what_worked + lesson iz hevristike."""
    r = RunReviewer(tmp_path / "memory.db")
    res = r.review({"project": "demo", "directive": "zgradi modul", "outcome": "green",
                    "traceback": "", "llm_calls": 2, "attempts": 1})
    assert res["root_cause"] == "correct"
    assert res["what_worked"]          # zeleni tek uči
    assert res["lesson"]               # uspeh ima lekcijo iz what_worked

    row = r.recent(limit=1)[0]
    assert row["what_worked"]
    assert "goal" in row               # shema ima strukturirana polja


def test_review_records_structured_goal_plan_task_type(tmp_path):
    """P1 — strukturirana polja task_lesson (goal, plan_summary, task_type) se zapišejo."""
    r = RunReviewer(tmp_path / "memory.db")
    res = r.review({
        "project": "demo", "directive": "zgradi API",
        "goal": "Zgradi avtentikacijski API", "plan": "Plan: FastAPI + auth",
        "task_type": "python", "outcome": "failed",
        "traceback": "ista napaka ValueError po 3 poskusih",
    })
    assert res["goal"] == "Zgradi avtentikacijski API"
    assert res["plan_summary"] == "Plan: FastAPI + auth"
    assert res["task_type"] == "python"
    assert res["what_failed"]          # rdeč tek ima what_failed
    row = r.recent(limit=1)[0]
    assert row["goal"] == "Zgradi avtentikacijski API"
    assert row["task_type"] == "python"


def test_review_includes_next_step_failed(tmp_path):
    """P6 — rdeč tek → next_step po vzroku (recurring_error → change_approach)."""
    r = RunReviewer(tmp_path / "memory.db")
    res = r.review({"project": "p", "directive": "d", "outcome": "failed",
                    "traceback": "ista napaka ValueError po 3 poskusih"})
    assert res["next_step"] == "change_approach"


def test_review_includes_next_step_green(tmp_path):
    """P6 — zelen tek → next_step continue."""
    r = RunReviewer(tmp_path / "memory.db")
    res = r.review({"project": "p", "directive": "d", "outcome": "green"})
    assert res["next_step"] == "continue"


def test_next_step_column_exists(tmp_path):
    """P6 — stolpec next_step obstaja v run_reviews (recent → dict)."""
    r = RunReviewer(tmp_path / "memory.db")
    r.review({"project": "p", "directive": "d", "outcome": "green"})
    row = r.recent(limit=1)[0]
    assert "next_step" in row


def test_recent_returns_reviews_newest_first(tmp_path):
    r = RunReviewer(tmp_path / "memory.db")
    r.review({"project": "a", "directive": "x", "outcome": "failed",
              "traceback": "ista napaka ValueError po 3 poskusih"})
    r.review({"project": "b", "directive": "y", "outcome": "green"})

    recent = r.recent()
    assert len(recent) == 2
    assert recent[0]["project"] == "b"  # najnovejši prvi


def test_review_writes_lesson_into_semantic_memory(tmp_path):
    """Konkretna lekcija gre takoj v semantic_memories (Zanka 1 → takoj priklicljiva)."""
    from core.memory_consolidation import MemoryConsolidator

    r = RunReviewer(tmp_path / "memory.db")
    r.review({"project": "billing", "directive": "x", "outcome": "failed",
              "traceback": "ista napaka ValueError po 3 poskusih"})

    cons = MemoryConsolidator(tmp_path / "memory.db")
    assert cons.stats()["semantic_memories"] == 1


def test_unknown_root_cause_fallback(tmp_path):
    """Brez prepoznavnega vzorca → root_cause = unknown."""
    r = RunReviewer(tmp_path / "memory.db")
    res = r.review({"project": "x", "directive": "y", "outcome": "failed", "traceback": "nekaj splošnega"})
    assert res["root_cause"] == "unknown"
