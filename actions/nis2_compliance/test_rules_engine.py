"""nis2_compliance — testi pravila engine (child #1 + #7 legal_ref, vse offline).

Konvencije repoja: tmp_path + monkeypatch, brez omrežja, fiksni ``now``.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance import rules_engine as re  # noqa: E402
from actions.nis2_compliance.rules_engine import (  # noqa: E402
    RulesNotFoundError,
    RulesValidationError,
    UnknownTierError,
    load_rules,
    validate_articles,
    validate_gap_coverage,
    validate_legal_refs,
    validate_rules,
    validate_tiers,
    get_obligations,
    get_tier_rules,
)

RULES_DIR = Path(__file__).resolve().parent / "rules"


def _real_articles() -> dict:
    return json.loads((RULES_DIR / "zinfv1_articles.json").read_text(encoding="utf-8"))


def _write_articles(tmp_path) -> Path:
    (tmp_path / "zinfv1_articles.json").write_text(
        json.dumps(_real_articles()), encoding="utf-8"
    )
    return tmp_path / "zinfv1_articles.json"


# ── Helper: minimalna validna rules dict ──────────────────────────────
def _base_rules() -> dict:
    return {
        "schema_version": "1.0",
        "categories": [
            {"id": 1, "name": "Varnostna dokumentacija (21. člen)"},
            {"id": 2, "name": "Ukrepi za obvladovanje tveganj (22. člen)"},
        ],
        "obligations": [
            {
                "obligation_id": "OBL-01",
                "category": 1,
                "legal_ref": {"clen": 21, "odstavek": 1, "tocka": 1},
                "title": "Politika varnosti omrežnih in informacijskih sistemov",
                "tier": ["bistveni", "pomembni"],
                "checklist": [
                    {"item_id": "OBL-01-01", "description": "IVP", "evidence_tip": "dokument"},
                    {"item_id": "OBL-01-02", "description": "Področne politike", "evidence_tip": "dokument"},
                ],
            },
            {
                "obligation_id": "OBL-02",
                "category": 2,
                "legal_ref": {"clen": 22, "odstavek": 2, "tocka": 1},
                "title": "Podpora vodstva",
                "tier": ["bistveni"],
                "checklist": [
                    {"item_id": "OBL-02-01", "description": "Dokazilo", "evidence_tip": "dokument"},
                ],
            },
        ],
    }


def _base_tiers() -> dict:
    return {
        "schema_version": "1.0",
        "tiers": {
            "bistveni": {
                "incident_reporting": {"early_warning_h": 24, "assessment_h": 72, "final_report_d": 30},
                "bcp_required": True,
                "supply_chain_formal": True,
                "risk_defaults": {"likelihood": 3, "impact": 3},
            },
            "pomembni": {
                "incident_reporting": {"early_warning_h": 24, "assessment_h": 72, "final_report_d": 30},
                "bcp_required": False,
                "supply_chain_formal": False,
                "risk_defaults": {"likelihood": 2, "impact": 2},
            },
        },
    }


# ── validate_rules ────────────────────────────────────────────────────
def test_validate_rules_valid_real_file():
    """AC1: realna datoteka — 8 kategorij, ~30+ obveznosti, legal_ref 20(3)."""
    data = json.loads((RULES_DIR / "zinfv1_rules.json").read_text(encoding="utf-8"))
    errors = validate_rules(data)
    assert errors == []
    cats = data["categories"]
    assert len(cats) == 8
    obligations = data["obligations"]
    assert len(obligations) >= 30
    assert len({o["category"] for o in obligations}) == 8  # vsaj 1 na kategorijo
    # AC11: menedžerski trening ima legal_ref 20(3) (NE 20(2)).
    trening = [o for o in obligations if o["obligation_id"] == "OBL-02"]
    assert trening and trening[0]["legal_ref"] == {"clen": 20, "odstavek": 3, "tocka": None}


def test_validate_rules_empty_returns_empty():
    assert validate_rules(_base_rules()) == []


def test_validate_rules_duplicate_obligation_id():
    rules = _base_rules()
    rules["obligations"].append(copy.deepcopy(rules["obligations"][0]))
    errors = validate_rules(rules)
    assert any("duplicate obligation_id: OBL-01" in e for e in errors)


def test_validate_rules_duplicate_item_id():
    rules = _base_rules()
    rules["obligations"][1]["checklist"].append(
        {"item_id": "OBL-01-01", "description": "dup", "evidence_tip": "log"}
    )
    errors = validate_rules(rules)
    assert any("duplicate item_id: OBL-01-01" in e for e in errors)


def test_validate_rules_orphan_item_id():
    rules = _base_rules()
    rules["obligations"][1]["checklist"].append(
        {"item_id": "OBL-99-01", "description": "orphan", "evidence_tip": "log"}
    )
    errors = validate_rules(rules)
    assert any("orphan item_id: OBL-99-01 (parent OBL-02)" in e for e in errors)


def test_validate_rules_invalid_category_zero():
    rules = _base_rules()
    rules["obligations"][0]["category"] = 0
    errors = validate_rules(rules)
    assert any("invalid category: 0" in e for e in errors)


def test_validate_rules_invalid_category_eleven():
    rules = _base_rules()
    rules["obligations"][0]["category"] = 11
    errors = validate_rules(rules)
    assert any("invalid category: 11" in e for e in errors)


def test_validate_rules_invalid_evidence_tip():
    rules = _base_rules()
    rules["obligations"][0]["checklist"][0]["evidence_tip"] = "xls"
    errors = validate_rules(rules)
    assert any("invalid evidence_tip: xls (OBL-01-01)" in e for e in errors)


def test_validate_rules_tier_outside_allowed():
    rules = _base_rules()
    rules["obligations"][0]["tier"] = ["bistveni", "ključni"]
    errors = validate_rules(rules)
    assert any("invalid tier" in e and "ključni" in e for e in errors)


def test_validate_rules_missing_legal_ref():
    rules = _base_rules()
    del rules["obligations"][0]["legal_ref"]
    errors = validate_rules(rules)
    assert any("legal_ref" in e and "OBL-01" in e for e in errors)


def test_validate_rules_invalid_legal_ref_shape():
    rules = _base_rules()
    rules["obligations"][0]["legal_ref"] = {"clen": "22", "odstavek": 2}
    errors = validate_rules(rules)
    assert any("legal_ref.clen ni int" in e and "OBL-01" in e for e in errors)


def test_validate_rules_deterministic_order():
    """AC10: isti input → isti vrstni red ob ponovnih klicih."""
    rules = _base_rules()
    rules["obligations"].append(copy.deepcopy(rules["obligations"][0]))
    rules["obligations"][0]["checklist"][0]["evidence_tip"] = "xls"
    rules["obligations"][1]["checklist"].append(
        {"item_id": "OBL-99-01", "description": "orphan", "evidence_tip": "log"}
    )
    first = validate_rules(rules)
    second = validate_rules(rules)
    assert first == second
    assert first == sorted(first)


# ── load_rules ────────────────────────────────────────────────────────
def test_load_rules_valid(tmp_path):
    """AC4: naloži in validira JSON-e (rules + tiers + articles) → RulesBundle."""
    (tmp_path / "zinfv1_rules.json").write_text(json.dumps(_base_rules()), encoding="utf-8")
    (tmp_path / "zinfv1_tiers.json").write_text(json.dumps(_base_tiers()), encoding="utf-8")
    _write_articles(tmp_path)
    bundle = load_rules(tmp_path)
    assert bundle.schema_version == "1.0"
    assert len(bundle.obligations) == 2
    assert "bistveni" in bundle.tiers
    # annex_ref se izpelje iz legal_ref (single source of truth).
    assert bundle.obligations[0].annex_ref == "ZInfV-1 21. člen (1) 1. točka"


def test_load_rules_invalid_collects_errors(tmp_path):
    """AC4: invalidna datoteka → RulesValidationError z zbranimi napakami."""
    rules = _base_rules()
    rules["obligations"].append(copy.deepcopy(rules["obligations"][0]))
    (tmp_path / "zinfv1_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (tmp_path / "zinfv1_tiers.json").write_text(json.dumps(_base_tiers()), encoding="utf-8")
    _write_articles(tmp_path)
    with pytest.raises(RulesValidationError) as ei:
        load_rules(tmp_path)
    assert any("duplicate obligation_id: OBL-01" in e for e in ei.value.errors)


def test_load_rules_unknown_schema_version_rejected(tmp_path):
    """AC4: neznana schema_version → zavrnitev."""
    rules = _base_rules()
    rules["schema_version"] = "0.9"
    (tmp_path / "zinfv1_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (tmp_path / "zinfv1_tiers.json").write_text(json.dumps(_base_tiers()), encoding="utf-8")
    _write_articles(tmp_path)
    with pytest.raises(RulesValidationError) as ei:
        load_rules(tmp_path)
    assert any("neznana schema_version" in e for e in ei.value.errors)


def test_load_rules_unknown_clen_rejected(tmp_path):
    """AC1: neznan legal_ref clen → RulesValidationError z imenom obveznosti."""
    rules = _base_rules()
    rules["obligations"][0]["legal_ref"] = {"clen": 99, "odstavek": 1, "tocka": None}
    (tmp_path / "zinfv1_rules.json").write_text(json.dumps(rules), encoding="utf-8")
    (tmp_path / "zinfv1_tiers.json").write_text(json.dumps(_base_tiers()), encoding="utf-8")
    _write_articles(tmp_path)
    with pytest.raises(RulesValidationError) as ei:
        load_rules(tmp_path)
    assert any("neznan legal_ref clen: 99 (OBL-01)" in e for e in ei.value.errors)


def test_load_rules_missing_file(tmp_path):
    """AC4: missing file → RulesNotFoundError."""
    with pytest.raises(RulesNotFoundError):
        load_rules(tmp_path)


def test_load_rules_real_files_ok():
    """Realne datoteke iz rules/ se naložijo (smoke)."""
    bundle = load_rules()
    assert len(bundle.categories) == 8
    assert len(bundle.obligations) >= 30


# ── validate_articles ─────────────────────────────────────────────────
def test_validate_articles_real():
    assert validate_articles(_real_articles()) == []


def test_validate_articles_unknown_shape():
    errors = validate_articles({"schema_version": "1.0", "articles": {}})
    assert errors == []


def test_validate_articles_bad_tocke_not_ascending():
    art = _real_articles()
    art["articles"]["21"]["paragraph_tocke"]["1"] = [1, 1, 3]
    errors = validate_articles(art)
    assert any("niso strogo naraščajoče" in e for e in errors)


# ── validate_legal_refs (child #7, AC1) ───────────────────────────────
def test_legal_refs_unknown_clen_names_obligation():
    rules = _base_rules()
    rules["obligations"][0]["legal_ref"] = {"clen": 42, "odstavek": 1, "tocka": None}
    errors = validate_legal_refs(rules, _real_articles())
    assert any("neznan legal_ref clen: 42 (OBL-01)" in e for e in errors)


def test_legal_refs_tocka_out_of_range():
    rules = _base_rules()
    rules["obligations"][0]["legal_ref"] = {"clen": 21, "odstavek": 1, "tocka": 9}
    errors = validate_legal_refs(rules, _real_articles())
    assert any("tocka 9 izven obsega 21(1) 1..8 (OBL-01)" in e for e in errors)


def test_legal_refs_tocka_on_non_enumerated_article():
    rules = _base_rules()
    rules["obligations"][0]["legal_ref"] = {"clen": 20, "odstavek": 3, "tocka": 4}
    errors = validate_legal_refs(rules, _real_articles())
    assert any("ki nima alinej" in e and "OBL-01" in e for e in errors)


def test_legal_refs_all_valid_empty():
    assert validate_legal_refs(_base_rules(), _real_articles()) == []


# ── gap check (child #7, AC2) ─────────────────────────────────────────
def test_gap_coverage_real_rules_zero_uncovered():
    """AC2: po realignmentu 0 uncovered — 22(2) 1..17 in 21(1) 1..8."""
    rules = json.loads((RULES_DIR / "zinfv1_rules.json").read_text(encoding="utf-8"))
    assert validate_gap_coverage(rules, _real_articles()) == []


def test_gap_coverage_reports_missing_alineas():
    """AC2: manjkajoča alineja → 'uncovered: 22(2) tocka N'."""
    rules = _base_rules()  # pokriva le 21(1) točka 1 in 22(2) točka 1
    missing = validate_gap_coverage(rules, _real_articles())
    assert any("uncovered: 21(1) tocka 2" in e for e in missing)
    assert any("uncovered: 22(2) tocka 2" in e for e in missing)
    assert any("uncovered: 22(2) tocka 14" in e for e in missing)
    assert any("uncovered: 22(2) tocka 17" in e for e in missing)


# ── validate_tiers ────────────────────────────────────────────────────
def test_validate_tiers_valid():
    assert validate_tiers(_base_tiers()) == []


def test_validate_tiers_unknown_tier():
    tiers = _base_tiers()
    tiers["tiers"]["ključni"] = dict(tiers["tiers"]["bistveni"])
    errors = validate_tiers(tiers)
    assert any("neznan tier: ključni" in e for e in errors)


def test_validate_tiers_negative_incident_deadline():
    tiers = _base_tiers()
    tiers["tiers"]["bistveni"]["incident_reporting"]["early_warning_h"] = -5
    errors = validate_tiers(tiers)
    assert any("negativen/ničelni incident rok" in e and "early_warning_h" in e for e in errors)


def test_validate_tiers_zero_incident_deadline():
    tiers = _base_tiers()
    tiers["tiers"]["bistveni"]["incident_reporting"]["final_report_d"] = 0
    errors = validate_tiers(tiers)
    assert any("negativen/ničelni incident rok" in e and "final_report_d" in e for e in errors)


def test_validate_tiers_non_bool_bcp():
    tiers = _base_tiers()
    tiers["tiers"]["bistveni"]["bcp_required"] = "yes"
    errors = validate_tiers(tiers)
    assert any("non-bool bcp_required" in e for e in errors)


def test_validate_tiers_non_bool_supply_chain():
    tiers = _base_tiers()
    tiers["tiers"]["bistveni"]["supply_chain_formal"] = 1
    errors = validate_tiers(tiers)
    assert any("non-bool supply_chain_formal" in e for e in errors)


# ── schemas strict (AC8) ─────────────────────────────────────────────
def test_schemas_strict_unknown_field_rejected():
    """AC8: neznano polje / napačen tip se zavrne (extra='forbid')."""
    from actions.nis2_compliance.schemas import ChecklistItem, Obligation

    obl = _base_rules()["obligations"][0]
    with pytest.raises(Exception):
        Obligation.model_validate({**obl, "bogus_field": 1})
    with pytest.raises(Exception):
        Obligation.model_validate({**obl, "category": "ena"})  # napačen tip
    item = obl["checklist"][0]
    with pytest.raises(Exception):
        ChecklistItem.model_validate({**item, "evidence_tip": "xls"})
    with pytest.raises(Exception):
        ChecklistItem.model_validate({**item, "unknown": True})


def test_schemas_strict_tier_rules():
    """AC8: TierRules strict — neznano polje se zavrne."""
    from actions.nis2_compliance.schemas import TierRules

    cfg = _base_tiers()["tiers"]["bistveni"]
    with pytest.raises(Exception):
        TierRules.model_validate({**cfg, "bogus": True})


def test_legal_ref_strict_and_annex_derived():
    """Child #7: LegalRef strict; Obligation.annex_ref se izpelje iz legal_ref."""
    from actions.nis2_compliance.schemas import LegalRef, Obligation

    lr = LegalRef(clen=22, odstavek=2, tocka=11)
    assert lr.tocka == 11
    obl = _base_rules()["obligations"][0]
    o = Obligation.model_validate(obl)
    assert o.annex_ref == "ZInfV-1 21. člen (1) 1. točka"


# ── get_obligations ───────────────────────────────────────────────────
def test_get_obligations_tier_filter(tmp_path):
    _write_bundle(tmp_path)
    bundle = load_rules(tmp_path)
    bistveni = get_obligations(bundle, "bistveni")
    pomembni = get_obligations(bundle, "pomembni")
    ids_b = {o.obligation_id for o in bistveni}
    ids_p = {o.obligation_id for o in pomembni}
    assert "OBL-01" in ids_b and "OBL-02" in ids_b
    assert "OBL-01" in ids_p
    assert "OBL-02" not in ids_p  # OBL-02 je samo bistveni
    # Neznan tier → UnknownTierError, nikoli prazno.
    with pytest.raises(UnknownTierError):
        get_obligations(bundle, "ključni")


def test_get_obligations_unknown_tier_raises():
    bundle = _bundle_from_files()
    with pytest.raises(UnknownTierError):
        get_obligations(bundle, "izven")


# ── get_tier_rules ────────────────────────────────────────────────────
def test_get_tier_rules_returns_pragovi():
    bundle = _bundle_from_files()
    bistveni = get_tier_rules(bundle, "bistveni")
    assert bistveni.bcp_required is True
    assert bistveni.supply_chain_formal is True
    assert bistveni.incident_reporting.early_warning_h == 24
    pomembni = get_tier_rules(bundle, "pomembni")
    assert pomembni.bcp_required is False


def test_get_tier_rules_unknown_tier_raises():
    bundle = _bundle_from_files()
    with pytest.raises(UnknownTierError):
        get_tier_rules(bundle, "ključni")


# ── helpers ───────────────────────────────────────────────────────────
def _write_bundle(tmp_path) -> bool:
    (tmp_path / "zinfv1_rules.json").write_text(json.dumps(_base_rules()), encoding="utf-8")
    (tmp_path / "zinfv1_tiers.json").write_text(json.dumps(_base_tiers()), encoding="utf-8")
    _write_articles(tmp_path)
    return True


def _bundle_from_files():
    return load_rules()


# ── runtime tolerance (AC9) ───────────────────────────────────────────
def test_runtime_loads_nis2_module():
    """AC9/AC10: actions.nis2_compliance.main se naloži, app obstaja."""
    from core import actions_runtime

    mod = actions_runtime._load_module("nis2_compliance")
    assert mod is not None
    assert hasattr(mod, "app")


def test_runtime_tolerant_to_missing_module():
    """AC9: modul brez main.py → None, ni crash."""
    from core import actions_runtime

    assert actions_runtime._load_module("totally_missing_module_zzz") is None
    assert actions_runtime._load_module("__bad-name__") is None


# ── Defensive branches (coverage gap, ship audit) ─────────────────────
def test_validate_rules_non_dict():
    """Non-dict input → fail-loud napaka (ne KeyError)."""
    errors = validate_rules(["ni objekt"])
    assert errors, "pričakovana vsaj ena napaka za non-dict"
    assert any("objekt" in e.lower() for e in errors)


def test_load_rules_missing_tiers_file(tmp_path):
    """Tiers datoteka manjka, rules obstaja → RulesNotFoundError (fail-loud)."""
    rules_f = tmp_path / "zinfv1_rules.json"
    rules_f.write_text(__import__("json").dumps(_base_rules()), encoding="utf-8")
    with pytest.raises(RulesNotFoundError):
        load_rules(tmp_path)


def test_load_rules_missing_articles_file(tmp_path):
    """Articles shema manjka → RulesNotFoundError (fail-loud, child #7)."""
    (tmp_path / "zinfv1_rules.json").write_text(json.dumps(_base_rules()), encoding="utf-8")
    (tmp_path / "zinfv1_tiers.json").write_text(json.dumps(_base_tiers()), encoding="utf-8")
    with pytest.raises(RulesNotFoundError):
        load_rules(tmp_path)


def test_load_rules_corrupt_json(tmp_path):
    """Pokvarjen JSON → napaka (RulesValidationError ali RulesNotFoundError — ne tih load)."""
    import json

    rules_f = tmp_path / "zinfv1_rules.json"
    rules_f.write_text("{ not valid json", encoding="utf-8")
    tiers_f = tmp_path / "zinfv1_tiers.json"
    tiers_f.write_text(json.dumps(_base_tiers()), encoding="utf-8")
    _write_articles(tmp_path)
    with pytest.raises((RulesValidationError, RulesNotFoundError)):
        load_rules(tmp_path)


def test_get_tier_rules_missing_tier_key_unknown_error():
    """Bundle, katerega tiers dict nima veljavnega tier ključa → UnknownTierError (ne KeyError)."""
    import types

    bundle = types.SimpleNamespace(tiers={})
    with pytest.raises(UnknownTierError):
        get_tier_rules(bundle, "bistveni")


def test_validate_tiers_risk_defaults_out_of_range():
    """risk_defaults izven 1-5 → napaka (fail-loud)."""
    tiers = _base_tiers()
    tiers["tiers"]["bistveni"]["risk_defaults"] = {"likelihood": 6, "impact": 0}
    errors = validate_tiers(tiers)
    assert any("risk_defaults" in e for e in errors)
