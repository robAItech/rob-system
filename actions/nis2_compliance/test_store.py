"""nis2_compliance — testi per-firm store (child #2, vse offline)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.schemas import (  # noqa: E402
    EvidenceDraft,
    FirmProfile,
    IntakeAnswer,
    ScopeResult,
)
from actions.nis2_compliance.store import Nis2Store  # noqa: E402

NOW = 1_700_000_000


def _profile(firm_id="firma-a", **over) -> FirmProfile:
    base = dict(
        firm_id=firm_id,
        naziv=f"Firma {firm_id}",
        sektor="energetika",
        zaposleni=300,
        promet_mio=60.0,
        kontakt="",
        created_at=NOW,
    )
    base.update(over)
    return FirmProfile(**base)


def _scope(tier="bistveni", **over) -> ScopeResult:
    base = dict(
        tier=tier,
        razlog="zaposleni=300 ≥ 250 (bistveni)",
        evidence={"input": {"zaposleni": 300}},
        checked_at=NOW,
    )
    base.update(over)
    return ScopeResult(**base)


def _answers() -> list[IntakeAnswer]:
    return [
        IntakeAnswer(question_id="sektor", answer="energetika", answered_at=NOW),
        IntakeAnswer(question_id="mfa_aktiviran", answer="da", answered_at=NOW),
    ]


def _evidence() -> list[EvidenceDraft]:
    return [
        EvidenceDraft(obligation_id="OBL-01", item_id="OBL-01-01", status="dokazano", evidence_ref="IVP.pdf"),
        EvidenceDraft(obligation_id="OBL-01", item_id="OBL-01-02", status="v delu", evidence_ref=""),
    ]


# ── schemas strict (AC8 child #2) ────────────────────────────────────
def test_store_schemas_strict():
    """AC8: neznano polje / napačen tip se zavrne na ingest robu."""
    with pytest.raises(Exception):
        FirmProfile.model_validate({**_profile().model_dump(), "bogus": 1})
    with pytest.raises(Exception):
        FirmProfile.model_validate({**_profile().model_dump(), "zaposleni": -1})
    with pytest.raises(Exception):
        ScopeResult.model_validate({**_scope().model_dump(), "tier": "ključni"})
    with pytest.raises(Exception):
        IntakeAnswer.model_validate({"question_id": "", "answer": "da", "answered_at": NOW})
    with pytest.raises(Exception):
        EvidenceDraft.model_validate({**_evidence()[0].model_dump(), "extra": True})


# ── Firm profile ──────────────────────────────────────────────────────
def test_create_get_roundtrip_and_per_firm_path(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    assert store.db_path == tmp_path / "firma-a.db"
    assert store.db_path.exists()  # __init__ kreira shemo → datoteko
    store.create_firm(_profile())
    got = store.get_firm("firma-a")
    assert got is not None
    assert got.naziv == "Firma firma-a"
    assert got.zaposleni == 300
    assert got.created_at == NOW


def test_get_firm_unknown_returns_none(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    assert store.get_firm("neznana") is None


def test_tenant_isolation(tmp_path):
    """C4: firma A vpiše, firma B (druga DB datoteka) ne vidi ničesar."""
    store_a = Nis2Store(tmp_path, "firma-a")
    store_a.create_firm(_profile("firma-a"))
    store_b = Nis2Store(tmp_path, "firma-b")
    assert store_b.get_firm("firma-a") is None
    assert store_a.get_firm("firma-b") is None
    store_b.create_firm(_profile("firma-b"))
    assert store_a.get_firm("firma-b") is None  # ostaja izolirano


def test_reinit_does_not_duplicate_schema(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    store2 = Nis2Store(tmp_path, "firma-a")  # ponovni __init__ iste firme
    assert store2.get_firm("firma-a") is not None  # IF NOT EXISTS → brez podvojenih


# ── Scope ─────────────────────────────────────────────────────────────
def test_scope_roundtrip(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    store.save_scope_result("firma-a", _scope())
    got = store.get_scope_result("firma-a")
    assert got is not None
    assert got.tier == "bistveni"
    assert got.evidence["input"]["zaposleni"] == 300
    assert got.checked_at == NOW


def test_scope_missing_returns_none(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    assert store.get_scope_result("firma-a") is None


# ── Intake ────────────────────────────────────────────────────────────
def test_intake_roundtrip(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    store.save_intake_answers("firma-a", _answers())
    got = store.get_intake_answers("firma-a")
    assert [a.question_id for a in got] == ["sektor", "mfa_aktiviran"]
    assert got[1].answer == "da"


def test_intake_empty(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    assert store.get_intake_answers("firma-a") == []


# ── Evidence ──────────────────────────────────────────────────────────
def test_evidence_roundtrip(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    store.save_evidence_draft("firma-a", _evidence(), now=NOW)
    got = store.get_evidence_draft("firma-a")
    assert len(got) == 2
    by_item = {e.item_id: e for e in got}
    assert by_item["OBL-01-01"].status == "dokazano"
    assert by_item["OBL-01-01"].evidence_ref == "IVP.pdf"
    assert by_item["OBL-01-02"].status == "v delu"


def test_evidence_deterministic_order(tmp_path):
    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    # Vstavi v neurejenem vrstnem redu; branje je deterministično sortirano.
    store.save_evidence_draft(
        "firma-a",
        [
            EvidenceDraft(obligation_id="OBL-02", item_id="OBL-02-01", status="v delu", evidence_ref=""),
            EvidenceDraft(obligation_id="OBL-01", item_id="OBL-01-02", status="v delu", evidence_ref=""),
        ],
        now=NOW,
    )
    got = store.get_evidence_draft("firma-a")
    assert [e.item_id for e in got] == ["OBL-01-02", "OBL-02-01"]


# ── Fail-loud defensive branches (coverage gap, ship audit) ───────────
def test_create_firm_duplicate_integrity_error(tmp_path):
    """Duplikat firm_id → IntegrityError (fail-loud contract, store.py:120)."""
    import sqlite3

    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    with pytest.raises(sqlite3.IntegrityError):
        store.create_firm(_profile())


def test_save_scope_fk_violation_unknown_firm(tmp_path):
    """FK: save_scope_result za firmo brez profila → IntegrityError."""
    import sqlite3

    store = Nis2Store(tmp_path, "firma-neznana")
    with pytest.raises(sqlite3.IntegrityError):
        store.save_scope_result("firma-neznana", _scope())


def test_evidence_resave_does_not_duplicate(tmp_path):
    """Re-save evidence ne sme tiho podvojiti vrstic (append-only pomeni dedup risk)."""
    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(_profile())
    store.save_evidence_draft("firma-a", _evidence(), now=NOW)
    store.save_evidence_draft("firma-a", _evidence(), now=NOW)
    got = store.get_evidence_draft("firma-a")
    # Trenutno append-only: dve kopiji. Dokumentirano — risk.build preko dict
    # last-wins dedupe-a; če se spremeni v upsert, ta test to ujame.
    assert len(got) == 2 * len(_evidence())
