"""nis2_compliance — pravila engine (ZInfV-1, child #1 + #7 pravni realignment).

Loader + validator + tier-parametrizacija deklarativnih pravil:

- ``rules/zinfv1_rules.json`` — obligation → legal_ref → checklist → evidence-tip
  (tematske kategorije zrcalijo člene ZInfV-1: 20/21/22/23/24/25/29/30).
- ``rules/zinfv1_tiers.json`` — tier pragovi (incident roki, BCP, supply chain).
- ``rules/zinfv1_articles.json`` — referenčna shema členov (child #7).

Child #7 dodaja strukturiran ``legal_ref`` ({clen, odstavek, tocka}) na vsaki
obveznosti + validator legal_ref proti referenčni shemi (fail-loud) + gap check
pokritosti 22(2) 1..17 in 21(1) 1..8 (``validate_gap_coverage``).

Deterministično, brez LLM, brez omrežja; error handling je fail-loud
(zero silent failures). Vrstni red napak validatorja je determinističen
(sorted po sporočilu).
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
ARTICLES_FILENAME = "zinfv1_articles.json"
SUPPORTED_SCHEMA_VERSION = "1.0"
VALID_TIERS = set(TIERS)

#: Gap check obsega pokritost alinej — 21(1) 8 dokumentov in 22(2) 17 ukrepov.
GAP_SCOPE: dict[int, int] = {21: 1, 22: 2}


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


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise RulesNotFoundError(f"Datoteka ni berljiva: {path}: {e}") from e


# ── Loader ────────────────────────────────────────────────────────────
def load_rules(path: Path | None = None) -> RulesBundle:
    """Naloži rules + tiers + articles JSON, validira VSE, vrne RulesBundle.

    Zavrne neznano schema_version (ni tihega load-a starega formata).
    Legal_ref vsake obveznosti se preveri proti referenčni shemi členov
    (child #7: neznan člen/tocka → napaka). Gap check (``validate_gap_coverage``)
    je izpostavljen ločeno (testi + eksplicitna uporaba), da partial bundles
    v unit testih ostanejo uporabni.

    Raises:
        RulesNotFoundError: datoteka ne obstaja / ni berljiva / ni valid JSON.
        RulesValidationError: zbrane napake datotek (deterministično).
    """
    rules_dir = Path(path) if path is not None else _default_rules_dir()
    rules_path = rules_dir / RULES_FILENAME
    tiers_path = rules_dir / TIERS_FILENAME
    articles_path = rules_dir / ARTICLES_FILENAME
    for p, name in ((rules_path, "Rules"), (tiers_path, "Tiers"), (articles_path, "Articles")):
        if not p.is_file():
            raise RulesNotFoundError(f"{name} datoteka ne obstaja: {p}")
    rules = _load_json(rules_path)
    tiers = _load_json(tiers_path)
    articles = _load_json(articles_path)
    errors = (
        validate_rules(rules)
        + validate_tiers(tiers)
        + validate_articles(articles)
        + validate_legal_refs(rules, articles)
    )
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


# ── Validator: rules ──────────────────────────────────────────────────
def validate_rules(rules: dict) -> list[str]:
    """Stroga strukturna validacija ``zinfv1_rules.json``.

    Vrne seznam napak v DETERMINISTIČNEM vrstnem redu (sorted) — empty = valid.
    Preverja: unikatni obligation_id + item_id; item_id prefix == parent
    obligation_id; validna category (v categories[]); validen evidence_tip;
    tier ⊆ {"bistveni","pomembni"}; legal_ref prisoten (strukturna oblika).
    (Legal_ref semanticno preverja ``validate_legal_refs`` proti articles shemi.)
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

        legal_ref = obl.get("legal_ref")
        if not isinstance(legal_ref, dict):
            errors.append(f"manjkajoc ali neveljaven legal_ref: {obligation_id}")
        else:
            clen = legal_ref.get("clen")
            odstavek = legal_ref.get("odstavek", 1)
            tocka = legal_ref.get("tocka")
            if not isinstance(clen, int):
                errors.append(f"legal_ref.clen ni int: {clen!r} ({obligation_id})")
            if not isinstance(odstavek, int):
                errors.append(f"legal_ref.odstavek ni int: {odstavek!r} ({obligation_id})")
            if tocka is not None and not isinstance(tocka, int):
                errors.append(f"legal_ref.tocka ni int ali null: {tocka!r} ({obligation_id})")

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


# ── Validator: articles shema ─────────────────────────────────────────
def validate_articles(articles: dict) -> list[str]:
    """Validacija referenčne sheme členov ``zinfv1_articles.json``.

    Preverja: schema_version; ``articles`` objekt; vsak člen ima ``title``;
    ``paragraph_tocke`` (če obstaja) so dict odstavek → naraščajoč seznam intov.
    """
    errors: list[str] = []
    if not isinstance(articles, dict):
        return ["articles mora biti JSON objekt"]
    if articles.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        errors.append(
            f"neznana schema_version: {articles.get('schema_version')!r} "
            f"(podprta: {SUPPORTED_SCHEMA_VERSION})"
        )
    art_map = articles.get("articles")
    if not isinstance(art_map, dict):
        errors.append("articles.articles mora biti objekt")
        return sorted(errors)
    for clen, cfg in art_map.items():
        if not isinstance(cfg, dict):
            errors.append(f"article {clen} mora biti objekt")
            continue
        if not isinstance(cfg.get("title"), str) or not cfg["title"].strip():
            errors.append(f"article {clen} brez title")
        pt = cfg.get("paragraph_tocke", {})
        if not isinstance(pt, dict):
            errors.append(f"article {clen}: paragraph_tocke mora biti objekt")
            continue
        for par, tocke in pt.items():
            if not isinstance(tocke, list) or not tocke:
                errors.append(f"article {clen}({par}): paragraph_tocke mora biti neprazen seznam")
                continue
            prev = 0
            for t in tocke:
                if not isinstance(t, int):
                    errors.append(f"article {clen}({par}): tocka ni int: {t!r}")
                elif t <= prev:
                    errors.append(f"article {clen}({par}): tocke niso strogo naraščajoče")
                prev = t if isinstance(t, int) else prev
    return sorted(errors)


# ── Validator: legal_ref proti shemi (child #7) ───────────────────────
def validate_legal_refs(rules: dict, articles: dict) -> list[str]:
    """Preveri legal_ref vsake obveznosti proti referenčni shemi členov.

    Fail-loud (AC1): neznan člen ali točka → napaka z imenom obveznosti.
    - člen mora obstajati v articles.articles;
    - če je točka podana, mora odstavek imeti alineje (paragraph_tocke) in
      točka mora biti v obsegu (npr. 22(2) 1..17, 21(1) 1..8).
    """
    errors: list[str] = []
    art_map = articles.get("articles") if isinstance(articles, dict) else None
    if not isinstance(art_map, dict):
        return ["articles shema manjka (articles.articles)"]
    obligations = rules.get("obligations") if isinstance(rules, dict) else []
    if not isinstance(obligations, list):
        return errors
    for obl in obligations:
        if not isinstance(obl, dict):
            continue
        obligation_id = obl.get("obligation_id", "")
        lr = obl.get("legal_ref")
        if not isinstance(lr, dict):
            continue  # strukturna napaka obravnavana v validate_rules
        clen = lr.get("clen")
        odstavek = lr.get("odstavek", 1)
        tocka = lr.get("tocka")
        key = str(clen)
        if key not in art_map:
            errors.append(f"neznan legal_ref clen: {clen} ({obligation_id})")
            continue
        valid_tocke = art_map[key].get("paragraph_tocke", {}).get(str(odstavek))
        if tocka is None:
            continue
        if not isinstance(valid_tocke, list) or not valid_tocke:
            errors.append(
                f"legal_ref tocka {tocka} na členu {clen}({odstavek}), ki nima alinej ({obligation_id})"
            )
            continue
        if tocka not in valid_tocke:
            errors.append(
                f"legal_ref tocka {tocka} izven obsega {clen}({odstavek}) "
                f"{valid_tocke[0]}..{valid_tocke[-1]} ({obligation_id})"
            )
    return sorted(errors)


# ── Gap check pokritosti alinej (AC2) ─────────────────────────────────
def validate_gap_coverage(rules: dict, articles: dict) -> list[str]:
    """Javi vsako alinejo 22(2) (1..17) in vsak dokument 21(1) (1..8), ki ni
    pokrit z nobeno obveznostjo (legal_ref na točno to alinejo).

    Po realignmentu mora biti rezultat prazen (0 uncovered).
    """
    covered: dict[tuple[int, int], set[int]] = {(c, o): set() for c, o in GAP_SCOPE.items()}
    obligations = rules.get("obligations") if isinstance(rules, dict) else []
    if not isinstance(obligations, list):
        return sorted(f"uncovered: {c}({o}) tocka {t}" for (c, o) in covered for t in [])
    art_map = articles.get("articles") if isinstance(articles, dict) else {}
    for obl in obligations:
        if not isinstance(obl, dict):
            continue
        lr = obl.get("legal_ref")
        if not isinstance(lr, dict):
            continue
        key = (lr.get("clen"), lr.get("odstavek", 1))
        t = lr.get("tocka")
        if key in covered and isinstance(t, int):
            covered[key].add(t)
    uncovered: list[str] = []
    for (clen, par) in sorted(covered):
        expected = set(art_map.get(str(clen), {}).get("paragraph_tocke", {}).get(str(par), []))
        for t in sorted(expected - covered[(clen, par)]):
            uncovered.append(f"uncovered: {clen}({par}) tocka {t}")
    return sorted(uncovered)


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
