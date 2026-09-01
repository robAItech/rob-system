"""nis2_compliance — Pydantic V2 sheme (ZInfV-1 / NIS2 done-for-you).

Deljene sheme vseh child-jev (pravila engine, store/scope/intake, politike/
ocena tveganj/API). Trda pravila (CEO review 2026-09-01):

- **Strict vhod**: ``strict=True, extra="forbid"`` — neznana polja / napačni
  tipi se zavrnejo na ingest robu.
- **Fail-loud**: domenske napake imajo imena (UnknownFirmError,
  InvalidScopeInputError, ...) in nosijo kontekst.
- Deterministično, brez LLM.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: Ne-prazen, strict string za identifikatorje (obligation_id, firm_id, ...).
StrictText = Annotated[str, StringConstraints(strict=True, min_length=1)]

#: Dovoljeni tipi dokazov (kako se dokazuje skladnost checklist postavke).
EVIDENCE_TIPS = ("dokument", "log", "izpis", "screenshot")
EvidenceTip = Literal["dokument", "log", "izpis", "screenshot"]

#: Obsega (tier-ja) po ZInfV-1 6./7. člen (pravila engine pozna samo ta dva).
TIERS = ("bistveni", "pomembni")

#: Status evidence postavke (pravila engine/intake generirata samo
#: "dokazano" ali "v delu"; preostala stanja pridejo s poznejšimi child-i).
EvidenceStatus = Literal["ni začeto", "v delu", "dokazano", "pregledano", "potrjeno"]


# ── Domenske napake (fail-loud, nosijo kontekst) ──────────────────────
class Nis2Error(Exception):
    """Bazni razred za domenske napake nis2_compliance."""


class UnknownFirmError(Nis2Error):
    """Firma ne obstaja v store-u (404 na API robu)."""


class InvalidScopeInputError(Nis2Error):
    """Negativen/neveljaven vhod za scope determinacijo."""


class ScopeNotDeterminedError(Nis2Error):
    """Intake pred scope (obseg še ni določen za firmo)."""


class PolicyNotFoundError(Nis2Error):
    """Predloga politike ne obstaja."""


class PolicyRenderError(Nis2Error):
    """Napaka pri renderiranju predloge (neznan/ne-substituiran placeholder)."""


class RiskBuildError(Nis2Error):
    """Napaka pri gradnji registra tveganj."""


# ── Child #1 — pravila engine ─────────────────────────────────────────
class Category(BaseModel):
    """Ena od 10 kategorij ukrepov iz Art 21(2) ZInfV-1."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: int = Field(ge=1, le=10)
    name: StrictText


class ChecklistItem(BaseModel):
    """Ena preverljiva postavka znotraj obligation-e (checklist)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    item_id: StrictText           # prefix = parent obligation_id (npr. OBL-01-01)
    description: StrictText
    evidence_tip: EvidenceTip     # kako se dokazuje (dokument/log/izpis/screenshot)


class Obligation(BaseModel):
    """Obveznost ZInfV-1: preslikava obligation → checklist → evidence-tip."""

    model_config = ConfigDict(strict=True, extra="forbid")

    obligation_id: StrictText
    category: int = Field(ge=1, le=10)       # reference na categories[].id
    annex_ref: StrictText                     # pravni vir (obvezen)
    title: StrictText
    tier: list[Literal["bistveni", "pomembni"]]
    checklist: list[ChecklistItem]


class IncidentReporting(BaseModel):
    """Roki za poročanje incidentov (ZInfV-1 Art 23)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    early_warning_h: int = Field(gt=0)
    assessment_h: int = Field(gt=0)
    final_report_d: int = Field(gt=0)


class RiskDefaults(BaseModel):
    """Privzeti likelihood/impact za oceno tveganj (ISO 27005 skala 1–5)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)


class TierRules(BaseModel):
    """Tier pragovi iz ``zinfv1_tiers.json`` (bistveni/pomembni)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    incident_reporting: IncidentReporting
    bcp_required: bool
    supply_chain_formal: bool
    risk_defaults: RiskDefaults = Field(
        default_factory=lambda: RiskDefaults(likelihood=3, impact=3)
    )


class RulesBundle(BaseModel):
    """Validirano pravilo bundle: kategorije + obveznosti + tier pragovi."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: StrictText
    categories: list[Category]
    obligations: list[Obligation]
    tiers: dict[str, TierRules]


# ── Child #2 — store / scope / intake ─────────────────────────────────
class FirmProfile(BaseModel):
    """Profil klienta (firma) — osnova vseh per-firm podatkov."""

    model_config = ConfigDict(strict=True, extra="forbid")

    firm_id: StrictText            # UUID4, generiran ob kreiranju
    naziv: StrictText
    sektor: StrictText             # normaliziran sektor
    zaposleni: int = Field(ge=0)
    promet_mio: float = Field(ge=0)   # EUR v mio
    kontakt: str = Field(default="", max_length=200)
    created_at: int


class ScopeInput(BaseModel):
    """Vhod za scope determinacijo (iz intake vprašalnika)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    zaposleni: int                 # ≥ 0 (negativen → InvalidScopeInputError)
    promet_mio: float              # ≥ 0, EUR v mio
    sektor: StrictText             # normaliziran sektor


class ScopeResult(BaseModel):
    """Izid obseg determinacije (E6): bistveni / pomembni / izven."""

    model_config = ConfigDict(strict=True, extra="forbid")

    tier: Literal["bistveni", "pomembni", "izven"]
    razlog: str                    # imenuje mejo, ki je odločila
    evidence: dict[str, Any]       # input vrednosti + uporabljene meje
    checked_at: int


class IntakeAnswer(BaseModel):
    """En odgovor iz strukturiranega intake vprašalnika (E7)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    question_id: StrictText        # npr. "zaposleni", "promet_mio", "sektor"
    answer: StrictText             # raw odgovor (številka/tekst)
    answered_at: int


class EvidenceDraft(BaseModel):
    """Draft evidence za en checklist item (intake → status)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    obligation_id: StrictText
    item_id: StrictText
    status: EvidenceStatus
    evidence_ref: str = ""


# ── Child #3 — politike / ocena tveganj / API ─────────────────────────
class PolicyDoc(BaseModel):
    """Renderana predloga politike s substituiranimi placeholderji."""

    model_config = ConfigDict(strict=True, extra="forbid")

    policy_id: StrictText          # npr. "informacijska-varnostna-politika"
    title: StrictText
    body_markdown: str             # renderana predloga (brez ne-substituiranih placeholderjev)
    rendered_at: int


class RiskItem(BaseModel):
    """Eno tveganje v registru (ISO/IEC 27005, SME-priredba)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    risk_id: StrictText            # npr. "RISK-01"
    category: int = Field(ge=1, le=10)   # iz rules categories
    description: str               # LLM-draft za prosti tekst, sicer generičen
    likelihood: int = Field(ge=1, le=5)  # ISO 27005 skala
    impact: int = Field(ge=1, le=5)
    score: int = Field(ge=1, le=25)      # likelihood × impact
    mitigation: StrictText         # ukrep
    owner: StrictText              # lastnik (default "direktor")
    deadline: str                  # ISO datum — default NIS2_DEADLINE
    evidence_ref: str              # iz evidence_draft (child #2)


class RiskRegister(BaseModel):
    """Determinističen register tveganj za firmo."""

    model_config = ConfigDict(strict=True, extra="forbid")

    firm_id: StrictText
    items: list[RiskItem]
    generated_at: int


class CreateFirmRequest(BaseModel):
    """Vhod za POST /firms — kreira firmo + scope + intake v enem koraku."""

    model_config = ConfigDict(strict=True, extra="forbid")

    naziv: StrictText
    sektor: StrictText
    zaposleni: int                 # negativen → InvalidScopeInputError (400)
    promet_mio: float
    kontakt: str = Field(default="", max_length=200)
    answers: list[IntakeAnswer] = Field(default_factory=list)
