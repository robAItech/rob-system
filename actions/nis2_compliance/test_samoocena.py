"""nis2_compliance — testi samoocene skladnosti (25. člen, child #7, offline)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.policies import render_all_policies  # noqa: E402
from actions.nis2_compliance.rules_engine import get_obligations, load_rules  # noqa: E402
from actions.nis2_compliance.samoocena import ODPRAVA_ROK_DNI, prepare_samoocena  # noqa: E402
from actions.nis2_compliance.schemas import (  # noqa: E402
    EvidenceDraft,
    FirmProfile,
    SamoocenaError,
    ScopeResult,
)

POLICIES_DIR = Path(__file__).resolve().parent / "rules" / "policies"
NOW = 1_700_000_000


def _firm(**over) -> FirmProfile:
    base = dict(
        firm_id="firma-a",
        naziv="Acme d.o.o.",
        sektor="proizvodnja",
        zaposleni=60,
        promet_mio=12.0,
        kontakt="jan.novak@example.com",
        created_at=NOW,
    )
    base.update(over)
    return FirmProfile(**base)


def _scope(tier="pomembni") -> ScopeResult:
    return ScopeResult(
        tier=tier,
        razlog="test",
        evidence={"input": {}},
        checked_at=NOW,
    )


def _evidence_all(tier: str, status="dokazano") -> list[EvidenceDraft]:
    """Vsa evidence tier-ja (razen 25. člena — samoocena ne ocenjuje sebe)."""
    bundle = load_rules()
    ev: list[EvidenceDraft] = []
    for obl in get_obligations(bundle, tier):
        if obl.legal_ref.clen == 25:
            continue
        for item in obl.checklist:
            ev.append(
                EvidenceDraft(
                    obligation_id=obl.obligation_id,
                    item_id=item.item_id,
                    status=status,
                    evidence_ref="dokazilo.pdf" if status == "dokazano" else "",
                )
            )
    return ev


def test_samoocena_skladno_izjava_o_skladnosti():
    """AC8: vse 'dokazano' → izjava o skladnosti (25(4))."""
    bundle = load_rules()
    report = prepare_samoocena(_firm(), _scope("pomembni"), _evidence_all("pomembni"), bundle, now=NOW)
    assert report.tier == "pomembni"
    assert report.vrsta == "samoocena"
    assert report.skladnost is True
    assert report.izjava is not None
    assert report.izjava.vrsta == "skladnosti"
    assert report.nacrt_odprave == []


def test_samoocena_neskladno_izjava_z_nacrtom_in_roki():
    """AC8: ena postavka 'v delu' → izjava o ugotavljanju neskladnosti (25(5))."""
    bundle = load_rules()
    ev = _evidence_all("pomembni")
    ev[0] = EvidenceDraft(
        obligation_id=ev[0].obligation_id, item_id=ev[0].item_id,
        status="v delu", evidence_ref="",
    )
    report = prepare_samoocena(_firm(), _scope("pomembni"), ev, bundle, now=NOW)
    assert report.skladnost is False
    assert report.izjava is not None
    assert report.izjava.vrsta == "ugotavljanje_neskladnosti"
    assert report.nacrt_odprave, "pričakovan načrt odprave neskladnosti"
    prvi = report.nacrt_odprave[0]
    expected_rok = (datetime.fromtimestamp(NOW).date() + timedelta(days=ODPRAVA_ROK_DNI)).isoformat()
    assert prvi.rok == expected_rok
    assert prvi.item_id == ev[0].item_id


def test_bistveni_revizijski_paket_brez_izjave():
    """AC8/bistveni: 25(1) → revizijski paket (ni generativno), izjava None."""
    bundle = load_rules()
    report = prepare_samoocena(_firm(), _scope("bistveni"), _evidence_all("bistveni"), bundle, now=NOW)
    assert report.vrsta == "revizijski_paket"
    assert report.tier == "bistveni"
    assert report.izjava is None
    assert report.items, "podatki za revizorja"
    assert report.skladnost is True


def test_samoocena_izven_tier_raises():
    """Samoocena za firmo 'izven' → SamoocenaError (fail-loud)."""
    bundle = load_rules()
    with pytest.raises(SamoocenaError):
        prepare_samoocena(_firm(), _scope("izven"), [], bundle, now=NOW)


def test_samoocena_deterministic():
    """Determinizem: isti vhod → isti izhod."""
    bundle = load_rules()
    a = prepare_samoocena(_firm(), _scope("pomembni"), _evidence_all("pomembni"), bundle, now=NOW)
    b = prepare_samoocena(_firm(), _scope("pomembni"), _evidence_all("pomembni"), bundle, now=NOW)
    assert a.model_dump() == b.model_dump()


def test_integration_policies_samoocena_izjava():
    """Integration: pravila → politike (8 dokumentov) → samoocena → izjava."""
    firm = _firm()
    scope = _scope("pomembni")
    docs = render_all_policies(POLICIES_DIR, firm, scope, rendered_at=NOW)
    assert len(docs) == 8  # 21(1) dokumentacija
    bundle = load_rules()
    # Delna skladnost → izjava o ugotavljanju neskladnosti.
    ev = _evidence_all("pomembni")
    ev[0] = EvidenceDraft(
        obligation_id=ev[0].obligation_id, item_id=ev[0].item_id,
        status="v delu", evidence_ref="",
    )
    report = prepare_samoocena(firm, scope, ev, bundle, now=NOW)
    assert report.izjava is not None
    assert report.izjava.vrsta == "ugotavljanje_neskladnosti"
    assert report.nacrt_odprave
