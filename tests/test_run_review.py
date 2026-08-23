"""tests/test_run_review.py — Zanka 2: post-run samoevalvacija odločitev.

Preveri: recenzent klasificira vzrok izida na nivoju odločitve, zapiše recenzijo
in (za konkretne neuspehe) vpiše lekcijo v semantični spomin (Zanka 1).
Testi prisilijo hevristično recenzijo (brez LLM/omrežja).
"""

from unittest import mock

import pytest

from core import agenda
from core.run_review import RunReviewer


@pytest.fixture(autouse=True)
def _force_heuristic(monkeypatch):
    """Izklopi LLM recenzijo — testi tečejo lokalno, brez omrežja."""
    monkeypatch.setattr(RunReviewer, "_llm_available", staticmethod(lambda: False))


@pytest.fixture
def iso_agenda(tmp_path, monkeypatch):
    """Fix-loop enqueue piše v tmp agenda.json (ne realni .rob_ai)."""
    monkeypatch.setattr(agenda, "AGENDA_FILE", tmp_path / "agenda.json")
    return agenda


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


# ------------------------------------------------------------------ #
#  C2 — zapri zanko neuspeha: maybe_enqueue_fix
# ------------------------------------------------------------------ #
def test_maybe_enqueue_fix_recurring_error_enqueues(tmp_path, iso_agenda):
    r = RunReviewer(tmp_path / "memory.db")
    run = {"project": "billing", "directive": "zgradi obračun", "outcome": "failed",
           "task_type": "python", "last_traceback": "test_billing() ValueError"}
    review = r.review({**run, "traceback": "ista napaka ValueError po 3 poskusih"})
    assert review["root_cause"] == "recurring_error"

    item = r.maybe_enqueue_fix(run, review)
    assert item is not None
    assert item["source"] == "fix_loop"
    assert item["target"] == "billing"
    assert item["kind"] == "python"
    assert item["status"] == "pending"
    assert any(i["id"] == item["id"] for i in iso_agenda.all_())


def test_fix_directive_consumes_next_step_and_test(tmp_path, iso_agenda):
    r = RunReviewer(tmp_path / "memory.db")
    run = {"project": "billing", "directive": "zgradi obračun", "outcome": "failed",
           "task_type": "python", "goal": "Zgradi obračun DDV",
           "last_traceback": 'File "test_billing.py", line 3, in test_billing\nValueError: bad'}
    review = r.review({**run, "traceback": "ista napaka ValueError po 3 poskusih"})
    item = r.maybe_enqueue_fix(run, review)
    g = item["goal"]
    assert "failing test <test_billing>" in g
    assert "next step <change_approach (" in g      # konzumira NEXT_STEP
    assert "CHANGE APPROACH" in g
    assert "green criterion = project tests pass" in g
    assert "ValueError" in g


def test_maybe_enqueue_fix_skips_green_and_non_fixable(tmp_path, iso_agenda):
    r = RunReviewer(tmp_path / "memory.db")
    # green → None
    run_g = {"project": "a", "directive": "x", "outcome": "green", "task_type": "python"}
    assert r.maybe_enqueue_fix(run_g, r.review({**run_g, "traceback": ""})) is None
    # test_gap → None (testi so test-locked)
    run_t = {"project": "b", "directive": "x", "outcome": "failed", "task_type": "python"}
    review_t = r.review({**run_t, "traceback": "test assert je napačen"})
    assert review_t["root_cause"] == "test_gap"
    assert r.maybe_enqueue_fix(run_t, review_t) is None
    # unknown → None
    run_u = {"project": "c", "directive": "x", "outcome": "failed", "task_type": "python"}
    review_u = r.review({**run_u, "traceback": "nekaj splošnega"})
    assert review_u["root_cause"] == "unknown"
    assert r.maybe_enqueue_fix(run_u, review_u) is None
    assert len(iso_agenda.all_()) == 0


def test_maybe_enqueue_fix_skips_non_python(tmp_path, iso_agenda):
    r = RunReviewer(tmp_path / "memory.db")
    run = {"project": "dok", "directive": "x", "outcome": "failed", "task_type": "markdown"}
    review = r.review({**run, "traceback": "ista napaka ValueError po 3 poskusih"})
    assert r.maybe_enqueue_fix(run, review) is None
    assert len(iso_agenda.all_()) == 0


def test_maybe_enqueue_fix_guard_max_attempts(tmp_path, iso_agenda):
    r = RunReviewer(tmp_path / "memory.db")
    for i in range(3):
        iso_agenda.add(f"fix {i}", kind="python", target="billing", source="fix_loop")
    run = {"project": "billing", "directive": "x", "outcome": "failed", "task_type": "python"}
    review = r.review({**run, "traceback": "ista napaka ValueError po 3 poskusih"})
    assert r.maybe_enqueue_fix(run, review) is None   # cap 3 dosežen
    assert len(iso_agenda.all_()) == 3


def test_maybe_enqueue_fix_guard_pending(tmp_path, iso_agenda):
    r = RunReviewer(tmp_path / "memory.db")
    iso_agenda.add("čakajoč fix", kind="python", target="billing", source="fix_loop")
    run = {"project": "billing", "directive": "x", "outcome": "failed", "task_type": "python"}
    review = r.review({**run, "traceback": "ista napaka ValueError po 3 poskusih"})
    assert r.maybe_enqueue_fix(run, review) is None   # že čaka pending fix
    assert len(iso_agenda.all_()) == 1


def test_maybe_enqueue_fix_never_raises(tmp_path, iso_agenda, monkeypatch):
    r = RunReviewer(tmp_path / "memory.db")
    run = {"project": "billing", "directive": "x", "outcome": "failed", "task_type": "python"}
    review = r.review({**run, "traceback": "ista napaka ValueError po 3 poskusih"})
    monkeypatch.setattr(agenda, "add", mock.Mock(side_effect=RuntimeError("boom")))
    assert r.maybe_enqueue_fix(run, review) is None   # build ne sme pasti


def test_extract_failing_test():
    assert RunReviewer._extract_failing_test(
        'File "test_billing.py", line 3, in test_billing\nValueError') == "test_billing"
    assert RunReviewer._extract_failing_test("") == ""
