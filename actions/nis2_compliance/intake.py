"""nis2_compliance — klient profil intake (E7, child #2).

Strukturiran vprašalnik → prvi draft evidence. DETERMINISTIČNO (D3):
odgovor prisoten + mapiran (question_map) → checklist item "dokazano";
brez mapiranja ali brez odgovora → "v delu" (ni tiho-generirane evidence).
Item, ki NI v obveznostih tier-ja → izpuščen.

``question_map`` je data, ne koda (``rules/intake_questions.json``) — čista
deterministična funkcija, testabilna z različnimi mapami.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.rules_engine import get_obligations  # noqa: E402
from actions.nis2_compliance.schemas import (  # noqa: E402
    EvidenceDraft,
    FirmProfile,
    IntakeAnswer,
    RulesBundle,
    SamoregistracijaInput,
    SamoregistracijaPaket,
    ScopeResult,
)

QUESTION_MAP_FILENAME = "intake_questions.json"


def _default_rules_dir() -> Path:
    env = os.environ.get("NIS2_RULES_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "rules"


def load_question_map(path: Path | None = None) -> dict[str, str]:
    """Naloži ``intake_questions.json`` → ``{question_id: item_id}``."""
    questions_path = (
        Path(path) if path is not None else _default_rules_dir()
    ) / QUESTION_MAP_FILENAME
    if not questions_path.is_file():
        raise FileNotFoundError(f"Question map ni najdena: {questions_path}")
    data = json.loads(questions_path.read_text(encoding="utf-8"))
    return dict(data.get("question_map", {}))


def intake_to_draft_evidence(
    answers: list[IntakeAnswer],
    bundle: RulesBundle,
    scope_result: ScopeResult,
    question_map: dict[str, str],
) -> list[EvidenceDraft]:
    """DETERMINISTIČNO: odgovor + mapiran → checklist item 'dokazano'.

    - strukturni odgovori (zaposleni, promet, sektor) → scope determinacija
      → firm_profile (tu se uporabi le ``scope_result.tier``);
    - scope_result tier → get_obligations(bundle, tier) → za vsak item:
        · odgovor obstaja ZA question_id, ki mapira na ta item → "dokazano"
          z evidence_ref = odgovor;
        · brez mapiranja ali brez odgovora → "v delu", evidence_ref="";
    - item, ki NI v get_obligations(tier) → izpuščen (ne velja za ta tier);
    - tier "izven" → prazna lista (firma ni zavezanec, ni obveznosti).
    """
    if scope_result.tier not in ("bistveni", "pomembni"):
        return []
    obligations = get_obligations(bundle, scope_result.tier)

    answer_by_qid = {a.question_id: a.answer for a in answers}
    item_to_qid: dict[str, str] = {}
    for qid, item_id in question_map.items():
        item_to_qid.setdefault(item_id, qid)

    drafts: list[EvidenceDraft] = []
    for obl in obligations:
        for item in obl.checklist:
            qid = item_to_qid.get(item.item_id)
            if qid is not None and answer_by_qid.get(qid, "").strip():
                drafts.append(
                    EvidenceDraft(
                        obligation_id=obl.obligation_id,
                        item_id=item.item_id,
                        status="dokazano",
                        evidence_ref=answer_by_qid[qid],
                    )
                )
            else:
                drafts.append(
                    EvidenceDraft(
                        obligation_id=obl.obligation_id,
                        item_id=item.item_id,
                        status="v delu",
                        evidence_ref="",
                    )
                )
    return drafts


def build_samoregistracija_paket(
    firm: FirmProfile,
    scope_result: ScopeResult,
    reg: SamoregistracijaInput,
    now: int | None = None,
) -> SamoregistracijaPaket:
    """Sestavi samoregistracijski paket za URSIV portal (ZInfV-1 8. člen).

    Modul pripravi podatkovni paket (8(2) 1., 5.–8. točka) — ne avtomatizira
    pošiljanja (portal izvedba je out of scope). Rok registracije: 30 dni.
    """
    ts = int(now) if now is not None else int(time.time())
    tier = scope_result.tier if scope_result.tier in ("bistveni", "pomembni") else None
    return SamoregistracijaPaket(
        firm_id=firm.firm_id,
        naziv=firm.naziv,
        sektor=firm.sektor,
        tier=tier,
        registracijski_rok_dni=30,
        podatki=reg,
        generated_at=ts,
    )
