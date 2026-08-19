"""tests/test_memory_consolidation.py — Zanka 1: spominska konsolidacija.

Preveri jedrni cikel: surove epizode (task_history) → semantične lekcije
(semantic_memories) → priklic (recall) → idempotenten cursor.

Testi prisilijo HEVRISTIČNO distilacijo (brez LLM/omrežja), da so hitri in
deterministični ne glede na to, ali je v okolju nastavljen DeepSeek ključ.
"""

import pytest

from core.memory_consolidation import MemoryConsolidator
from core.gbrain_bridge import GBrainBridge


@pytest.fixture(autouse=True)
def _force_heuristic(monkeypatch):
    """Izklopi LLM distilacijo — testi tečejo lokalno, brez omrežja."""
    monkeypatch.setattr(MemoryConsolidator, "_llm_available", staticmethod(lambda: False))


def _make_consolidator(tmp_path):
    return MemoryConsolidator(tmp_path / "memory.db")


def _record_failure(gbrain: GBrainBridge, project: str, error: str, mitigation: str):
    gbrain.record_task(
        project,
        f"zgradi modul {project}",
        "FAILED",
        traceback=f"\n{error}: neka napaka pri izvajanju\n",
        verified_code="Fail",
    )
    gbrain.add_blacklist_pattern(project, error, mitigation)


def test_consolidate_turns_failures_into_pitfall_memories(tmp_path):
    cons = _make_consolidator(tmp_path)
    gbrain = GBrainBridge(tmp_path / "memory.db")

    _record_failure(gbrain, "demo", "NameError", "definiraj spremenljivko pred uporabo")

    res = cons.consolidate()
    assert res["new_episodes"] == 1
    assert res["mode"] == "heuristic"
    assert res["created"] >= 1

    stats = cons.stats()
    assert stats["semantic_memories"] >= 1
    assert stats["by_kind"].get("pitfall", 0) >= 1


def test_consolidation_is_idempotent_via_cursor(tmp_path):
    cons = _make_consolidator(tmp_path)
    gbrain = GBrainBridge(tmp_path / "memory.db")
    _record_failure(gbrain, "demo", "NameError", "definiraj spremenljivko pred uporabo")

    first = cons.consolidate()
    second = cons.consolidate()

    assert first["new_episodes"] == 1
    assert second["new_episodes"] == 0  # cursor se je premaknil → ni podvajanja


def test_recall_returns_relevant_lessons(tmp_path):
    cons = _make_consolidator(tmp_path)
    gbrain = GBrainBridge(tmp_path / "memory.db")
    _record_failure(gbrain, "demo", "NameError", "definiraj spremenljivko pred uporabo")
    cons.consolidate()

    hits = cons.recall("NameError", project="demo")
    assert hits, "recall mora vrniti relevantno lekcijo"
    assert hits[0]["kind"] == "pitfall"
    assert "NameError" in hits[0]["theme"]


def test_recall_returns_empty_for_unrelated_query(tmp_path):
    cons = _make_consolidator(tmp_path)
    gbrain = GBrainBridge(tmp_path / "memory.db")
    _record_failure(gbrain, "demo", "NameError", "definiraj spremenljivko pred uporabo")
    cons.consolidate()

    assert cons.recall("popolnoma nepovezana poizvedba xyzq") == []


def test_successful_episodes_do_not_produce_noise(tmp_path):
    """Uspešni teki brez napake ne smejo generirati pitfall lekcij."""
    cons = _make_consolidator(tmp_path)
    gbrain = GBrainBridge(tmp_path / "memory.db")
    gbrain.record_task("demo", "zgradi", "VERIFIED GREEN", traceback="", verified_code="Pass")

    res = cons.consolidate()
    assert res["created"] == 0  # nič za strdit iz uspešnega teka


def test_probe_projects_are_excluded(tmp_path):
    """Prehodne sonde/testi (_loopx_probe, test_*, …) se ne strdijo v spomin."""
    cons = _make_consolidator(tmp_path)
    gbrain = GBrainBridge(tmp_path / "memory.db")

    # Sonda (izključena) + pravi neuspeh (vključen).
    _record_failure(gbrain, "_loopx_probe", "NameError", "x")
    _record_failure(gbrain, "billing", "NameError", "definiraj spremenljivko pred uporabo")

    res = cons.consolidate()
    assert res["probes_skipped"] == 1
    assert res["created"] == 1  # samo billing, ne _loopx_probe

    stats = cons.stats()
    assert stats["semantic_memories"] == 1
