"""nis2_compliance — testi intake → draft evidence (child #2, E7, offline)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.intake import (  # noqa: E402
    build_samoregistracija_paket,
    intake_to_draft_evidence,
    load_question_map,
)
from actions.nis2_compliance.rules_engine import load_rules  # noqa: E402
from actions.nis2_compliance.schemas import (  # noqa: E402
    FirmProfile,
    IntakeAnswer,
    SamoregistracijaInput,
    ScopeResult,
)

RULES_DIR = Path(__file__).resolve().parent / "rules"
NOW = 1_700_000_000


def _bundle():
    return load_rules()


def _scope(tier="bistveni") -> ScopeResult:
    return ScopeResult(
        tier=tier,
        razlog="test",
        evidence={"input": {}},
        checked_at=NOW,
    )


def _answers() -> list[IntakeAnswer]:
    return [
        IntakeAnswer(question_id="register_sredstev", answer="Inventar.xlsx", answered_at=NOW),
        IntakeAnswer(question_id="mfa_aktiviran", answer="da", answered_at=NOW),
        IntakeAnswer(question_id="sektor", answer="energetika", answered_at=NOW),
    ]


def _real_map() -> dict[str, str]:
    return load_question_map()


def test_real_question_map_loads():
    qmap = _real_map()
    assert isinstance(qmap, dict) and len(qmap) >= 1
    # Vsak mapiran item_id dejansko obstaja v rules.
    bundle = _bundle()
    item_ids = {i.item_id for o in bundle.obligations for i in o.checklist}
    assert set(qmap.values()) <= item_ids


def test_deterministic_mapping():
    """AC6: strukturni odgovori → scope → mapirani itemi 'dokazano'."""
    bundle = _bundle()
    qmap = _real_map()
    drafts = intake_to_draft_evidence(_answers(), bundle, _scope("bistveni"), qmap)
    # Determinizem: ponovni klic da isto zaporedje.
    drafts2 = intake_to_draft_evidence(_answers(), bundle, _scope("bistveni"), qmap)
    assert [d.item_id for d in drafts] == [d.item_id for d in drafts2]
    by_item = {d.item_id: d for d in drafts}
    assert by_item["OBL-06-01"].status == "dokazano"      # register_sredstev (21(1)(2))
    assert by_item["OBL-27-02"].status == "dokazano"      # mfa_aktiviran (22(2)(15))
    assert by_item["OBL-27-02"].evidence_ref == "da"
    assert by_item["OBL-01-01"].status == "v delu"        # ni mapiran


def test_unmapped_questions_are_v_delu():
    """AC6: brez mapiranja ali brez odgovora → 'v delu' (ni tihe evidence)."""
    bundle = _bundle()
    drafts = intake_to_draft_evidence(_answers(), bundle, _scope("bistveni"), {})
    assert all(d.status == "v delu" for d in drafts)
    assert all(d.evidence_ref == "" for d in drafts)


def test_item_outside_tier_skipped():
    """AC6: item izven tier-ja → izpuščen."""
    bundle = _bundle()
    # OBL-32 (25(1) revizija) je samo bistveni; pri pomembni tier-ju izpuščen.
    drafts_p = intake_to_draft_evidence(
        [], bundle, _scope("pomembni"), _real_map()
    )
    item_ids_p = {d.item_id for d in drafts_p}
    assert not any(i.startswith("OBL-32-") for i in item_ids_p)
    drafts_b = intake_to_draft_evidence([], bundle, _scope("bistveni"), _real_map())
    item_ids_b = {d.item_id for d in drafts_b}
    assert any(i.startswith("OBL-32-") for i in item_ids_b)


def test_izven_tier_empty():
    """Firma 'izven' → ni obveznosti → prazen seznam."""
    bundle = _bundle()
    drafts = intake_to_draft_evidence(_answers(), bundle, _scope("izven"), _real_map())
    assert drafts == []


def test_intake_save_get_evidence_roundtrip(tmp_path):
    """Integration: intake → save → get evidence round-trip."""
    from actions.nis2_compliance.schemas import FirmProfile
    from actions.nis2_compliance.store import Nis2Store

    store = Nis2Store(tmp_path, "firma-a")
    store.create_firm(
        FirmProfile(
            firm_id="firma-a", naziv="Firma A", sektor="energetika",
            zaposleni=300, promet_mio=60.0, kontakt="", created_at=NOW,
        )
    )
    store.save_intake_answers("firma-a", _answers())
    bundle = _bundle()
    drafts = intake_to_draft_evidence(
        store.get_intake_answers("firma-a"), bundle, _scope("bistveni"), _real_map()
    )
    store.save_evidence_draft("firma-a", drafts, now=NOW)
    got = store.get_evidence_draft("firma-a")
    by_item = {d.item_id: d for d in got}
    assert by_item["OBL-06-01"].status == "dokazano"
    assert by_item["OBL-06-01"].evidence_ref == "Inventar.xlsx"
    assert by_item["OBL-01-01"].status == "v delu"


def test_blank_answer_v_delu():
    """Prazn/whitespace odgovor → 'v delu' (strip guard, intake.py:83)."""
    qmap = _real_map()
    # Poisci en item v mapi, ki obstaja v rules.
    mapped_item = next(iter(qmap.values()))
    answers = [IntakeAnswer(question_id="sektor", answer="energetika", answered_at=NOW)]
    drafts = intake_to_draft_evidence(answers, _bundle(), _scope("bistveni"), qmap)
    # Noben odgovor ni mapiran na qmap ključ (sektor ni v qmap) → vse v delu.
    assert drafts, "pričakovano vsaj en draft"
    assert all(d.status in ("dokazano", "v delu") for d in drafts)
    # Blank odgovor na ključ, ki JE v mapi → v delu.
    key = next(k for k in qmap if qmap[k] == mapped_item)
    blank = [IntakeAnswer(question_id=key, answer="   ", answered_at=NOW)]
    drafts2 = intake_to_draft_evidence(blank, _bundle(), _scope("bistveni"), qmap)
    assert any(d.item_id == mapped_item and d.status == "v delu" for d in drafts2)


def test_load_question_map_missing_file():
    """load_question_map z neobstoječim path → FileNotFoundError (fail-loud)."""
    import pytest as _pytest
    with _pytest.raises(FileNotFoundError):
        load_question_map(RULES_DIR / "ne-obstaja.json")


def test_samoregistracija_paket_fields():
    """AC10: samoregistracija polja — kontakt + namestnik + matična + IP + domene."""
    reg = SamoregistracijaInput(
        kontaktna_oseba_iv="Ana Novak",
        kontaktna_oseba_namestnik="Bojan Kovač",
        elektronski_naslov="info@acme.si",
        maticna_stevilka="12345678",
        ip_bloki=["193.2.1.0/24"],
        domene=["acme.si"],
        as_stevilke=["AS12345"],
        drzave_clanice_eu=["Slovenija", "Hrvaška"],
    )
    firm = FirmProfile(
        firm_id="firma-a", naziv="Acme d.o.o.", sektor="proizvodnja",
        zaposleni=60, promet_mio=12.0, kontakt="", created_at=NOW,
    )
    paket = build_samoregistracija_paket(firm, _scope("pomembni"), reg, now=NOW)
    assert paket.firm_id == "firma-a"
    assert paket.tier == "pomembni"
    assert paket.registracijski_rok_dni == 30  # 8(2): 30 dni
    assert paket.podatki.kontaktna_oseba_iv == "Ana Novak"
    assert paket.podatki.kontaktna_oseba_namestnik == "Bojan Kovač"
    assert paket.podatki.maticna_stevilka == "12345678"
    assert paket.podatki.ip_bloki == ["193.2.1.0/24"]
    assert paket.podatki.domene == ["acme.si"]
    assert paket.generated_at == NOW
