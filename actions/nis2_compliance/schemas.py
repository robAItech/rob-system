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

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


class SamoocenaError(Nis2Error):
    """Samoocena skladnosti (25. člen) ni izvedljiva (firma ni zavezanec)."""


# ── Child #1 — pravila engine ─────────────────────────────────────────
class LegalRef(BaseModel):
    """Strukturirana pravna referenca na ZInfV-1 člen (child #7 realignment).

    Primer: 22. člen (2) 11. točka → ``{"clen": 22, "odstavek": 2, "tocka": 11}``.
    ``tocka`` je alineja samo tam, kjer člen našteva (22(2) = 1..17,
    21(1) = 1..8); sicer ``None``.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    clen: int                                  # 20, 21, 22, 23, 24, 25, 29, 30
    odstavek: int = 1                          # odstavek člena
    tocka: int | None = None                   # alineja (22(2) 1..17; 21(1) 1..8)


def format_legal_ref(ref: LegalRef) -> str:
    """Človeško berljiv pravni sklic, izpeljan iz strukturiranega legal_ref.

    Npr. ``{"clen":22,"odstavek":2,"tocka":11}`` → ``"ZInfV-1 22. člen (2) 11. točka"``.
    """
    parts = [f"{ref.clen}. člen"]
    parts.append(f"({ref.odstavek})")
    if ref.tocka is not None:
        parts.append(f"{ref.tocka}. točka")
    return f"ZInfV-1 {' '.join(parts)}"


class Category(BaseModel):
    """Ena od tematskih kategorij, ki zrcalijo člene ZInfV-1 (child #7)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: int = Field(ge=1, le=8)
    name: StrictText


class ChecklistItem(BaseModel):
    """Ena preverljiva postavka znotraj obligation-e (checklist)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    item_id: StrictText           # prefix = parent obligation_id (npr. OBL-01-01)
    description: StrictText
    evidence_tip: EvidenceTip     # kako se dokazuje (dokument/log/izpis/screenshot)


class Obligation(BaseModel):
    """Obveznost ZInfV-1: preslikava obligation → legal_ref → checklist.

    ``annex_ref`` (človeško berljiv sklic) se VEDNO izpelje iz ``legal_ref``
    (single source of truth) — podatek v JSON-u se ne upošteva, da ne pride
    do razhajanja med strukturo in besedilom.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    obligation_id: StrictText
    category: int = Field(ge=1, le=8)       # reference na categories[].id
    legal_ref: LegalRef                       # strukturiran pravni vir (obvezen)
    annex_ref: str = ""                       # izpeljan iz legal_ref (human-readable)
    title: StrictText
    tier: list[Literal["bistveni", "pomembni"]]
    checklist: list[ChecklistItem]

    @model_validator(mode="after")
    def _derive_annex_ref(self) -> "Obligation":
        self.annex_ref = format_legal_ref(self.legal_ref)
        return self


class IncidentReporting(BaseModel):
    """Roki za poročanje incidentov (ZInfV-1 30(1): 24h/72h/1 mesec)."""

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
    """Vhod za scope determinacijo (iz intake vprašalnika, child #7).

    Pragovi so OR znotraj posameznega tier-ja in AND med zaposlenimi in
    prometom/bilančno vsoto za pomembne — glej scope.py. ``kategorija="posebna"``
    pomeni posebno kategorijo (DNS/TLD/kvalificirane storitve zaupanja,
    državna uprava) → bistveni ne glede na velikost (ZInfV-1 7(2)).
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    zaposleni: int                    # ≥ 0 (negativen → InvalidScopeInputError)
    promet_mio: float = Field(ge=0, allow_inf_nan=False, default=0.0)   # ≥ 0, EUR v mio (NaN/Inf → reject)
    bilancna_vsota_mio: float = Field(ge=0, allow_inf_nan=False, default=0.0)   # ≥ 0, EUR v mio (NaN/Inf → reject)
    sektor: StrictText                # normaliziran sektor (Priloga 1/2 ali "drug")
    kategorija: Literal["splosno", "posebna"] = "splosno"


class ScopeResult(BaseModel):
    """Izid obseg determinacije (E6): bistveni / pomembni / izven."""

    model_config = ConfigDict(strict=True, extra="forbid")

    tier: Literal["bistveni", "pomembni", "izven"]
    razlog: str                    # imenuje mejo, ki je odločila (tudi bilančno vsoto)
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
    """Renderana predloga dokumentacije 21. člena s substituiranimi placeholderji.

    ``legal_ref`` kaže na 21. člen (1) N. točko (8 dokumentov) — politike so
    mapirane na varnostno dokumentacijo ZInfV-1 (child #7).
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    policy_id: StrictText          # npr. "informacijska-varnostna-politika"
    title: StrictText
    legal_ref: LegalRef            # 21. člen (1) N. točka dokumentacije
    body_markdown: str             # renderana predloga (brez ne-substituiranih placeholderjev)
    rendered_at: int


class RiskItem(BaseModel):
    """Eno tveganje v registru (ISO/IEC 27005, SME-priredba)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    risk_id: StrictText            # npr. "RISK-01"
    category: int = Field(ge=1, le=8)   # iz rules categories
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


# ── Child #7 — samoregistracija (8. člen) ─────────────────────────────
class SamoregistracijaInput(BaseModel):
    """Samoregistracijski podatki zavezanca (ZInfV-1 8(2)).

    Modul pripravi PAKET za URSIV portal — ne avtomatizira pošiljanja
    (portal izvedba je out of scope).
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    kontaktna_oseba_iv: StrictText          # kontaktna oseba za IV (8(2) 5. t.)
    kontaktna_oseba_namestnik: StrictText   # namestnik (8(2) 5. t.)
    elektronski_naslov: str = ""            # e-naslov za vročanje (8(2) 1. t.)
    maticna_stevilka: StrictText            # matična številka (8(2) 1. t.)
    ip_bloki: list[str] = Field(default_factory=list)     # dodeljeni bloki javnih IP (8(2) 6. t.)
    domene: list[str] = Field(default_factory=list)       # registrirana domenska imena (8(2) 8. t.)
    as_stevilke: list[str] = Field(default_factory=list)  # registrirane številke AS (8(2) 8. t.)
    drzave_clanice_eu: list[str] = Field(default_factory=list)  # države članice (8(2) 7. t.)


class CreateFirmRequest(BaseModel):
    """Vhod za POST /firms — kreira firmo + scope + intake v enem koraku."""

    model_config = ConfigDict(strict=True, extra="forbid")

    naziv: StrictText
    sektor: StrictText
    zaposleni: int                 # negativen → InvalidScopeInputError (400)
    promet_mio: float = Field(ge=0, allow_inf_nan=False, default=0.0)   # ≥ 0, EUR v mio (NaN/Inf → reject)
    bilancna_vsota_mio: float = Field(ge=0, allow_inf_nan=False, default=0.0)   # ≥ 0, EUR v mio (NaN/Inf → reject)
    kategorija: Literal["splosno", "posebna"] = "splosno"
    kontakt: str = Field(default="", max_length=200)
    answers: list[IntakeAnswer] = Field(default_factory=list)
    samoregistracija: SamoregistracijaInput | None = None


# ── Child #7 — samoregistracija paket + samoocena (25. člen) ───────────
class SamoregistracijaPaket(BaseModel):
    """Paket podatkov za samoregistracijo na URSIV (8. člen, 30 dni)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    firm_id: StrictText
    naziv: StrictText
    sektor: StrictText
    tier: Literal["bistveni", "pomembni"] | None
    registracijski_rok_dni: int = 30         # 8(2): 30 dni od nastopa okoliščin
    podatki: SamoregistracijaInput
    generated_at: int


class SamoocenaUgotovitev(BaseModel):
    """Ena postavka v samooceni: skladnost checklist itema z obveznostjo."""

    model_config = ConfigDict(strict=True, extra="forbid")

    obligation_id: StrictText
    item_id: StrictText
    opis: StrictText
    status: EvidenceStatus
    skladno: bool


class OdpravaNacrt(BaseModel):
    """Postavka načrta odprave neskladnosti (25(5)) — ukrep + rok."""

    model_config = ConfigDict(strict=True, extra="forbid")

    item_id: StrictText
    ugotovitev: StrictText
    ukrep: StrictText
    rok: str                       # ISO datum (rok za izvedbo)


class SamoocenaIzjava(BaseModel):
    """Izjava pomembnega subjekta po samooceni (25(4)/(5))."""

    model_config = ConfigDict(strict=True, extra="forbid")

    vrsta: Literal["skladnosti", "ugotavljanje_neskladnosti"]
    besedilo: StrictText


class SamoocenaReport(BaseModel):
    """Izroček 25. člena: samoocena (pomembni) ali revizijski paket (bistveni).

    - pomembni (25(3)): dokumentirana samoocena → izjava o skladnosti
      (25(4)) ali izjava o ugotavljanju neskladnosti z načrtom odprave (25(5)).
    - bistveni (25(1)): ocena skladnosti se izvede kot revizija — modul
      pripravi podatke za revizorja (ni generativno), ``izjava`` je ``None``.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    firm_id: StrictText
    tier: Literal["bistveni", "pomembni"]
    vrsta: Literal["samoocena", "revizijski_paket"]
    skladnost: bool
    ocenjeno_at: int
    items: list[SamoocenaUgotovitev]
    izjava: SamoocenaIzjava | None
    nacrt_odprave: list[OdpravaNacrt]
