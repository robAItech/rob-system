"""nis2_compliance — testi politik (child #3, D1 deterministično, offline)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.policies import (  # noqa: E402
    POLICY_TITLES,
    build_user_notice,
    render_all_policies,
    render_policy,
)
from actions.nis2_compliance.schemas import (  # noqa: E402
    FirmProfile,
    PolicyNotFoundError,
    PolicyRenderError,
    ScopeResult,
)

POLICIES_DIR = Path(__file__).resolve().parent / "rules" / "policies"
NOW = 1_700_000_000


def _firm(**over) -> FirmProfile:
    base = dict(
        firm_id="firma-a",
        naziv="Acme d.o.o.",
        sektor="energetika",
        zaposleni=300,
        promet_mio=60.0,
        kontakt="jan.novak@example.com",
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


def test_render_policy_placeholder_substitution():
    """AC1: vsi placeholderji substituirani, output nima '{{'."""
    doc = render_policy(POLICIES_DIR / "informacijska-varnostna-politika.md", _firm(), _scope())
    assert "Acme d.o.o." in doc.body_markdown
    assert "energetika" in doc.body_markdown
    assert "bistveni" in doc.body_markdown
    assert "jan.novak@example.com" in doc.body_markdown
    assert "{{" not in doc.body_markdown
    assert doc.policy_id == "informacijska-varnostna-politika"
    assert doc.title == POLICY_TITLES["informacijska-varnostna-politika"]


def test_render_policy_tier_placeholder():
    """AC1: tier-specific placeholder ({{bcp_scope}}) substituiran."""
    doc = render_policy(POLICIES_DIR / "bcp.md", _firm(), _scope("bistveni"))
    assert "{{" not in doc.body_markdown
    assert "RTO/RPO" in doc.body_markdown  # poln BCP za bistveni


def test_render_all_policies_both_tiers_8():
    """AC4: OBA tier-ja dobita vseh 8 dokumentov 21(1)."""
    bistveni = render_all_policies(POLICIES_DIR, _firm(), _scope("bistveni"))
    pomembni = render_all_policies(POLICIES_DIR, _firm(), _scope("pomembni"))
    assert len(bistveni) == 8
    assert len(pomembni) == 8
    assert {p.policy_id for p in bistveni} == {p.policy_id for p in pomembni}


def test_policies_cover_all_8_documents_legal_ref():
    """AC4: 8 politik pokriva vseh 8 dokumentov 21(1); legal_ref → 21(1) N. točka."""
    docs = render_all_policies(POLICIES_DIR, _firm(), _scope("bistveni"))
    tocke = sorted(p.legal_ref.tocka for p in docs)
    assert tocke == [1, 2, 3, 4, 5, 6, 7, 8]
    assert all(p.legal_ref.clen == 21 and p.legal_ref.odstavek == 1 for p in docs)
    assert all(p.legal_ref.tocka is not None for p in docs)


def test_render_all_policies_tier_content_differs():
    """AC4: tier prilagoditev — bistveni poln BCP (RTO/RPO), pomembni mehkejši."""
    bistveni = {p.policy_id: p for p in render_all_policies(POLICIES_DIR, _firm(), _scope("bistveni"))}
    pomembni = {p.policy_id: p for p in render_all_policies(POLICIES_DIR, _firm(), _scope("pomembni"))}
    assert "RTO/RPO" in bistveni["bcp"].body_markdown
    assert "RTO/RPO" not in pomembni["bcp"].body_markdown


def test_render_all_policies_deterministic_hash():
    """AC3: isti vhod → isti output (hash primerjava)."""
    a = render_all_policies(POLICIES_DIR, _firm(), _scope("bistveni"), rendered_at=NOW)
    b = render_all_policies(POLICIES_DIR, _firm(), _scope("bistveni"), rendered_at=NOW)
    ha = [hashlib.sha256(p.body_markdown.encode("utf-8")).hexdigest() for p in a]
    hb = [hashlib.sha256(p.body_markdown.encode("utf-8")).hexdigest() for p in b]
    assert ha == hb


def test_render_policy_missing_template_raises():
    with pytest.raises(PolicyNotFoundError):
        render_policy(POLICIES_DIR / "ne-obstaja.md", _firm(), _scope())


def test_render_policy_unknown_placeholder_error(tmp_path):
    """Predloga z neznanim placeholderjem → PolicyRenderError (fail-loud, policies.py:126)."""
    bad = tmp_path / "bad.md"
    bad.write_text("# Politika\n{{neobstojec_placeholder}}\n", encoding="utf-8")
    with pytest.raises(PolicyRenderError):
        render_policy(bad, _firm(), _scope("bistveni"))


def test_build_user_notice_29_6():
    """AC9: predloga obvestila uporabnikom (29(6)) + ukrepi (29(7)), brez '{{'."""
    notice = build_user_notice(_firm(), _scope("bistveni"), incident_opis="Izpadi storitve", rendered_at=NOW)
    assert notice.policy_id == "obvestilo-uporabnikom"
    assert notice.legal_ref.clen == 29 and notice.legal_ref.odstavek == 6
    assert "Acme d.o.o." in notice.body_markdown
    assert "29(6)" in notice.body_markdown
    assert "29(7)" in notice.body_markdown
    assert "ukrepi, ki jih lahko uporabniki sprejmejo" in notice.body_markdown.lower()
    assert "{{" not in notice.body_markdown


def test_render_all_policies_izven_fallback():
    """'izven' scope → fallback tier substitucije (mehkejši pragovi), vseh 8 politik."""
    docs = render_all_policies(POLICIES_DIR, _firm(), _scope("izven"))
    assert len(docs) == 8
    # Noben output nima nedorečenega placeholderja.
    for d in docs:
        assert "{{" not in d.body_markdown
