"""nis2_compliance — ISO/IEC 27005 ocena tveganj (SME-priredba, child #3).

Register JE determinističen (likelihood/impact/score iz pravil, ne LLM);
LLM je SAMO za opis tveganja (prosti tekst), in to kot draft za človeško
potrditev. Retry + fallback prek ``DeepSeekLLMClient``; če LLM ni na voljo
→ generičen opis, ni blokada.

Preslikava (eno pravilo): evidence item s statusom "v delu" → RiskItem;
item "dokazano" → izpuščen iz registra (ne "izpuščen ali nizko").
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings  # noqa: E402
from actions.pii_masking_sanitizer.pii import PIIMasker  # noqa: E402
from actions.nis2_compliance.rules_engine import (  # noqa: E402
    get_obligations,
    get_tier_rules,
)
from actions.nis2_compliance.schemas import (  # noqa: E402
    EvidenceDraft,
    FirmProfile,
    RiskItem,
    RiskRegister,
    RulesBundle,
    ScopeResult,
)

#: Privzeti ukrep po kategoriji (iz pravila — deterministično, ne LLM).
CATEGORY_MITIGATIONS: dict[int, str] = {
    1: "Vzpostaviti in izvajati varnostne politike ter redno analizo tveganj",
    2: "Vzpostaviti postopek obvladovanja in poročanja incidentov",
    3: "Vzpostaviti načrt neprekinjenosti poslovanja in varnostno kopiranje",
    4: "Vzpostaviti obvladovanje varnosti dobavne verige",
    5: "Uvesti varnostne zahteve pri nabavi in razvoju",
    6: "Vzpostaviti politiko kriptografije in upravljanja ključev",
    7: "Uvesti program varnostne ozaveščenosti in usposabljanja kadrov",
    8: "Vzpostaviti nadzor dostopa in upravljanje identitet",
    9: "Vzpostaviti monitoring in beleženje varnostnih dogodkov",
    10: "Vzpostaviti upravljanje ranljivosti in popravkov",
}

DEFAULT_MITIGATION = "Uvesti ustrezne varnostne ukrepe po ZInfV-1"

#: Fail-closed fallback za PII redakcijo (nikoli raw LLM tekst v DB).
_GENERIC_DESC_FALLBACK = "Opis tveganja ni na voljo (redakcija ni uspela)."

#: Async funkcija (prompt → opis tveganja), npr. DeepSeekLLMClient.
LLMDescFn = Callable[[str], Awaitable[str]]


def _now() -> int:
    return int(time.time())


def _generic_description(obl, item) -> str:
    return (
        f"Nepokrito področje: {obl.title} ({item.item_id}) — "
        "vzpostaviti dokazilo in ukrepe za skladnost."
    )


def _redact_pii(text: str) -> str:
    """Redakcija PII (email/telefon/IBAN) pred shranitvijo opisa.

    FAIL-CLOSED (security specialist, CRITICAL): če redakcija pade, se vrne
    generičen opis (NE raw tekst) — PII nikoli ne pristane v DB neodredaktiran.
    """
    try:
        return PIIMasker().redact_text(text)
    except Exception:  # noqa: BLE001
        return _GENERIC_DESC_FALLBACK


async def build_risk_register(
    firm: FirmProfile,
    scope: ScopeResult,
    evidence: list[EvidenceDraft],
    bundle: RulesBundle,
    llm_desc: bool = True,
    llm_desc_fn: LLMDescFn | None = None,
    now: int | None = None,
) -> RiskRegister:
    """Determinističen register + opcijski LLM opis (draft za človeka).

    - za vsak obligation (iz get_obligations(tier)) → RiskItem, kjer evidence
      "v delu" kaže na tveganje (nepokrito = potencialno tveganje);
    - likelihood/impact/score: iz pravila (default iz zinfv1_tiers.json) —
      DETERMINISTIČNO, ne LLM ocena;
    - description: če ``llm_desc=True`` IN ``llm_desc_fn`` obstaja → LLM-draft
      (PII-redakcija); sicer generičen opis (fallback, ni blokada);
    - mitigation/owner/deadline: iz pravila ali default (direktor, NIS2_DEADLINE);
    - evidence "dokazano" → izpuščen iz registra;
    - tier "izven" → prazen register (firma ni zavezanec).
    """
    ts = int(now) if now is not None else _now()
    if scope.tier not in ("bistveni", "pomembni"):
        return RiskRegister(firm_id=firm.firm_id, items=[], generated_at=ts)

    tier_rules = get_tier_rules(bundle, scope.tier)
    defaults = tier_rules.risk_defaults
    obligations = get_obligations(bundle, scope.tier)
    evidence_by_item = {e.item_id: e for e in evidence}

    items: list[RiskItem] = []
    for obl in obligations:
        for item in obl.checklist:
            ev = evidence_by_item.get(item.item_id)
            if ev is not None and ev.status == "dokazano":
                continue  # izpuščen iz registra (eno pravilo)
            likelihood = defaults.likelihood
            impact = defaults.impact
            description = _generic_description(obl, item)
            if llm_desc and llm_desc_fn is not None:
                raw = await llm_desc_fn(
                    f"Obligation {obl.obligation_id} ({obl.title}): "
                    f"checklist {item.item_id} — {item.description}. "
                    f"evidence_ref={ev.evidence_ref if ev else ''}"
                )
                if raw and raw.strip():
                    description = _redact_pii(raw.strip())
            items.append(
                RiskItem(
                    risk_id=f"RISK-{len(items) + 1:02d}",
                    category=obl.category,
                    description=description,
                    likelihood=likelihood,
                    impact=impact,
                    score=likelihood * impact,
                    mitigation=CATEGORY_MITIGATIONS.get(obl.category, DEFAULT_MITIGATION),
                    owner="direktor",
                    deadline=settings.nis2_deadline,
                    evidence_ref=ev.evidence_ref if ev else "",
                )
            )
    return RiskRegister(firm_id=firm.firm_id, items=items, generated_at=ts)
