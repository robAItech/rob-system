"""nis2_compliance — pravila engine (ZInfV-1, child #1).

Loader + validator + tier-parametrizacija deklarativnih pravil:

- ``rules/zinfv1_rules.json`` — obligation → checklist → evidence-tip
  (10 kategorij Art 21(2) + Art 20(2) menedžerski trening).
- ``rules/zinfv1_tiers.json`` — tier pragovi (incident roki, BCP, supply chain).

Deterministično, brez LLM, brez omrežja; error handling je fail-loud
(zero silent failures). Vrstni red napak validatorja je determinističen
(sorted po obligation_id, nato item_id).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.schemas import (  # noqa: E402
    Category,
    EVIDENCE_TIPS,
    Obligation,
    RulesBundle,
    TierRules,
    TIERS,
)

RULES_FILENAME = "zinfv1_rules.json"
TIERS_FILENAME = "zinfv1_tiers.json"
SUPPORTED_SCHEMA_VERSION = "1.0"
VALID_TIERS = set(TIERS)


# ── Izjeme (fail-loud, nosijo kontekst) ───────────────────────────────
class RulesValidationError(Exception):
    """Nevalidna rules datoteka — nosi seznam napak (``errors: list[str]``)."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        detail = "; ".join(self.errors)
        super().__init__(f"Nevalidna rules datoteka: {detail}" if detail else "Nevalidna rules datoteka.")


class RulesNotFoundError(Exception):
    """Rules datoteka ne obstaja / ni berljiva."""


class UnknownTierError(Exception):
    """Neznan tier (ni v zinfv1_tiers.json). FAIL-LOUD, ne tiho prazno."""


# ── Path resolvers ────────────────────────────────────────────────────
def _default_rules_dir() -> Path:
    """Default rules imenik; ``NIS2_RULES_PATH`` env override doda per-firm paths."""
    env = os.environ.get("NIS2_RULES_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "rules"


# ── Loader ────────────────────────────────────────────────────────────
def load_rules(path: Path | None = None) -> RulesBundle:
    """Naloži zinfv1_rules.json + zinfv1_tiers.json, validira OBA, vrne RulesBundle.

    Zavrne neznano schema_version (ni tihega load-a starega formata).

    Raises:
        RulesNotFoundError: datoteka ne obstaja / ni berljiva / ni valid JSON.
        RulesValidationError: zbrane napake obeh datotek (deterministično).
    """
    rules_dir = Path(path) if path is not None else _default_rules_dir()
    rules_path = rules_dir / RULES_FILENAME
    tiers_path = rules_dir / TIERS_FILENAME
    if not rules_path.is_file():
        raise RulesNotFoundError(f"Rules datoteka ne obstaja: {rules_path}")
    if not tiers_path.is_file():
        raise RulesNotFoundError(f"Tiers datoteka ne obstaja: {tiers_path}")
    try:
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise RulesNotFoundError(f"Rules datoteka ni berljiva: {rules_path}: {e}") from e
    try:
        tiers = json.loads(tiers_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise RulesNotFoundError(f"Tiers datoteka ni berljiva: {tiers_path}: {e}") from e
    errors = validate_rules(rules) + validate_tiers(tiers)
    if errors:
        raise RulesValidationError(errors)
    return _build_bundle(rules, tiers)


def _build_bundle(rules: dict, tiers: dict) -> RulesBundle:
    return RulesBundle(
        schema_version=rules["schema_version"],
        categories=[Category(**c) for c in rules["categories"]],
        obligations=[Obligation(**o) for o in rules["obligations"]],
        tiers={name: TierRules(**cfg) for name, cfg in tiers["tiers"].items()},
    )


# ── Validatorja ───────────────────────────────────────────────────────
def validate_rules(rules: dict) -> list[str]:
    """Stroga validacija ``zinfv1_rules.json``.

    Vrne seznam napak v DETERMINISTIČNEM vrstnem redu (sorted) — empty = valid.
    Preverja: unikatni obligation_id + item_id; item_id prefix == parent
    obligation_id; validna category (v categories[]); validen evidence_tip;
    tier ⊆ {"bistveni","pomembni"}; annex_ref non-empty.
    """
    errors: list[str] = []
    if not isinstance(rules, dict):
        return ["rules mora biti JSON objekt"]

    if rules.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        errors.append(
            f"neznana schema_version: {rules.get('schema_version')!r} "
            f"(podprta: {SUPPORTED_SCHEMA_VERSION})"
        )

    categories = rules.get("categories")
    if not isinstance(categories, list):
        errors.append("categories mora biti seznam")
        categories = []
    cat_ids = [c.get("id") for c in categories if isinstance(c, dict)]

    obligations = rules.get("obligations")
    if not isinstance(obligations, list):
        errors.append("obligations mora biti seznam")
        obligations = []

    seen_obl: set[str] = set()
    seen_item: set[str] = set()
    for obl in obligations:
        if not isinstance(obl, dict):
            errors.append("obligation mora biti objekt")
            continue
        obligation_id = obl.get("obligation_id", "")
        if not isinstance(obligation_id, str) or not obligation_id:
            errors.append("obligation brez obligation_id")
            continue
        if obligation_id in seen_obl:
            errors.append(f"duplicate obligation_id: {obligation_id}")
        seen_obl.add(obligation_id)

        category = obl.get("category")
        if category not in cat_ids:
            errors.append(f"invalid category: {category} ({obligation_id})")

        annex_ref = obl.get("annex_ref")
        if not isinstance(annex_ref, str) or not annex_ref.strip():
            errors.append(f"prazen annex_ref: {obligation_id}")

        tier = obl.get("tier")
        if not isinstance(tier, list) or not tier:
            errors.append(f"invalid tier: {tier!r} ({obligation_id})")
        else:
            for t in tier:
                if t not in VALID_TIERS:
                    errors.append(f"invalid tier: {t!r} ({obligation_id})")

        checklist = obl.get("checklist")
        if not isinstance(checklist, list):
            errors.append(f"checklist manjka: {obligation_id}")
            checklist = []
        for item in checklist:
            if not isinstance(item, dict):
                errors.append(f"checklist item mora biti objekt ({obligation_id})")
                continue
            item_id = item.get("item_id", "")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"checklist item brez item_id ({obligation_id})")
                continue
            if item_id in seen_item:
                errors.append(f"duplicate item_id: {item_id}")
            seen_item.add(item_id)
            if not item_id.startswith(obligation_id + "-"):
                errors.append(f"orphan item_id: {item_id} (parent {obligation_id})")
            evidence_tip = item.get("evidence_tip")
            if evidence_tip not in EVIDENCE_TIPS:
                errors.append(f"invalid evidence_tip: {evidence_tip} ({item_id})")
            description = item.get("description")
            if not isinstance(description, str) or not description.strip():
                errors.append(f"prazen description: {item_id}")

    return sorted(errors)


def validate_tiers(tiers: dict) -> list[str]:
    """Validacija ``zinfv1_tiers.json``.

    Preverja: schema_version; tiers ključi ⊆ {"bistveni","pomembni"};
    incident_reporting ura/dnevi pozitivni; bcp_required/supply_chain_formal
    bool; risk_defaults (če prisoten) likelihood/impact v 1–5.
    """
    errors: list[str] = []
    if not isinstance(tiers, dict):
        return ["tiers mora biti JSON objekt"]

    if tiers.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        errors.append(
            f"neznana schema_version: {tiers.get('schema_version')!r} "
            f"(podprta: {SUPPORTED_SCHEMA_VERSION})"
        )

    tier_cfgs = tiers.get("tiers")
    if not isinstance(tier_cfgs, dict):
        errors.append("tiers.tiers mora biti objekt")
        tier_cfgs = {}

    for name, cfg in tier_cfgs.items():
        if name not in VALID_TIERS:
            errors.append(f"neznan tier: {name}")
            continue
        if not isinstance(cfg, dict):
            errors.append(f"tier konfiguracija mora biti objekt: {name}")
            continue
        reporting = cfg.get("incident_reporting")
        if not isinstance(reporting, dict):
            errors.append(f"incident_reporting manjka: {name}")
        else:
            for key in ("early_warning_h", "assessment_h", "final_report_d"):
                val = reporting.get(key)
                if not isinstance(val, int) or val <= 0:
                    errors.append(f"negativen/ničelni incident rok: {name}.{key}={val!r}")
        for key in ("bcp_required", "supply_chain_formal"):
            val = cfg.get(key)
            if not isinstance(val, bool):
                errors.append(f"non-bool {key}: {name}={val!r}")
        risk_defaults = cfg.get("risk_defaults")
        if risk_defaults is not None:
            if not isinstance(risk_defaults, dict):
                errors.append(f"risk_defaults mora biti objekt: {name}")
            else:
                for key in ("likelihood", "impact"):
                    val = risk_defaults.get(key)
                    if not isinstance(val, int) or not (1 <= val <= 5):
                        errors.append(f"risk_defaults.{key} izven 1-5: {name}={val!r}")

    return sorted(errors)


# ── Tier parametrizacija ──────────────────────────────────────────────
def get_obligations(bundle: RulesBundle, tier: str) -> list[Obligation]:
    """Filtrira obligation-e po tier-ju. Neznan tier → UnknownTierError."""
    if tier not in VALID_TIERS:
        raise UnknownTierError(f"Neznan tier: {tier!r}")
    return [o for o in bundle.obligations if tier in o.tier]


def get_tier_rules(bundle: RulesBundle, tier: str) -> TierRules:
    """Vrne tier pragove. Neznan tier → UnknownTierError (ne KeyError)."""
    if tier not in VALID_TIERS:
        raise UnknownTierError(f"Neznan tier: {tier!r}")
    try:
        return bundle.tiers[tier]
    except KeyError:
        raise UnknownTierError(f"Tier {tier!r} nima pravil v zinfv1_tiers.json") from None
