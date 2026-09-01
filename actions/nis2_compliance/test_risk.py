"""nis2_compliance — testi ISO 27005 ocene tveganj (child #3, D2, offline).

``build_risk_register`` je async; pytest config ``asyncio_mode = auto`` požene
``async def test_*`` samodejno.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.rules_engine import load_rules  # noqa: E402
from actions.nis2_compliance.risk import build_risk_register  # noqa: E402
from actions.nis2_compliance.schemas import (  # noqa: E402
    EvidenceDraft,
    FirmProfile,
    ScopeResult,
)

NOW = 1_700_000_000


def _bundle():
    return load_rules()


def _firm(**over) -> FirmProfile:
    base = dict(
        firm_id="firma-a",
        naziv="Acme d.o.o.",
        sektor="energetika",
        zaposleni=300,
        promet_mio=60.0,
        kontakt="",
        created_at=NOW,
    )
    base.update(over)
    return FirmProfile(**base)


def _scope(tier="bistveni") -> ScopeResult:
    return ScopeResult(
        tier=tier,
        razlog="zaposleni=300 ≥ 250 (bistveni)",
        evidence={"input": {}},
        checked_at=NOW,
    )


def _evidence(*items) -> list[EvidenceDraft]:
    return [
        EvidenceDraft(obligation_id=i[0], item_id=i[1], status=i[2], evidence_ref=i[3] or "")
        for i in items
    ]


async def test_deterministic_register_no_llm():
    """AC4: llm_desc=False → isti vhod → isti register (isti score, isti opisi)."""
    ev = _evidence(("OBL-01", "OBL-01-01", "v delu", ""), ("OBL-01", "OBL-01-02", "v delu", ""))
    a = await build_risk_register(_firm(), _scope(), ev, _bundle(), llm_desc=False, now=NOW)
    b = await build_risk_register(_firm(), _scope(), ev, _bundle(), llm_desc=False, now=NOW)
    assert a.model_dump() == b.model_dump()
    assert len(a.items) >= 2
    for item in a.items:
        assert 1 <= item.likelihood <= 5
        assert 1 <= item.impact <= 5
        assert item.score == item.likelihood * item.impact
        assert "Nepokrito področje" in item.description


async def test_v_delu_in_register_dokazano_excluded():
    """AC5: 'v delu' → v register; 'dokazano' → izpuščen (eno pravilo)."""
    ev = _evidence(
        ("OBL-01", "OBL-01-01", "dokazano", "IVP.pdf"),
        ("OBL-01", "OBL-01-02", "v delu", ""),
    )
    register = await build_risk_register(_firm(), _scope(), ev, _bundle(), llm_desc=False, now=NOW)
    descs = [i.description for i in register.items]
    # Generični opis vsebuje item_id → "OBL-01-02" (v delu) je v registru.
    assert any("OBL-01-02" in d for d in descs)
    # "OBL-01-01" (dokazano) je izpuščen.
    assert all("OBL-01-01" not in d for d in descs)
    # OBL-01 ima 2 itema; 1 je dokazano → v registru ostane 1 item OBL-01-*.
    obl01 = [i for i in register.items if "OBL-01" in i.description]
    assert len(obl01) == 1


async def test_llm_desc_false_generic_descriptions():
    """AC6a: llm_desc=False → generični opisi, brez LLM."""
    register = await build_risk_register(
        _firm(), _scope(), _evidence(("OBL-01", "OBL-01-01", "v delu", "")),
        _bundle(), llm_desc=False, now=NOW,
    )
    assert all("Nepokrito področje" in i.description for i in register.items)


async def test_llm_desc_true_without_fn_fallback():
    """AC6b: llm_desc=True brez LLM funkcije → fallback generičen (ni crash)."""
    register = await build_risk_register(
        _firm(), _scope(), _evidence(("OBL-01", "OBL-01-01", "v delu", "")),
        _bundle(), llm_desc=True, llm_desc_fn=None, now=NOW,
    )
    assert len(register.items) >= 1
    assert all("Nepokrito področje" in i.description for i in register.items)


async def test_pii_redaction_of_llm_description():
    """PII: LLM opis se redigira (email/telefon) pred shranitvijo."""
    async def _stub_desc(prompt: str) -> str:
        return "Kontakt: jan.novak@example.com, tel: +386 40 123 456"

    register = await build_risk_register(
        _firm(), _scope(), _evidence(("OBL-01", "OBL-01-01", "v delu", "")),
        _bundle(), llm_desc=True, llm_desc_fn=_stub_desc, now=NOW,
    )
    desc = register.items[0].description
    assert "jan.novak@example.com" not in desc
    assert "[email-REDACTED]" in desc
    assert "[phone-REDACTED]" in desc


async def test_izven_tier_empty_register():
    """Firma 'izven' → prazen register (ni zavezanec)."""
    register = await build_risk_register(
        _firm(), _scope("izven"), [], _bundle(), llm_desc=False, now=NOW
    )
    assert register.items == []
    assert register.firm_id == "firma-a"


async def test_risk_defaults_from_tiers():
    """D2: likelihood/impact iz zinfv1_tiers.json risk_defaults (bistveni 3/3)."""
    register = await build_risk_register(
        _firm(), _scope("bistveni"),
        _evidence(("OBL-01", "OBL-01-01", "v delu", "")),
        _bundle(), llm_desc=False, now=NOW,
    )
    assert register.items[0].likelihood == 3
    assert register.items[0].impact == 3
    assert register.items[0].score == 9
    assert register.items[0].owner == "direktor"
    assert register.items[0].deadline == "2026-12-19"
