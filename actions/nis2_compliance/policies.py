"""nis2_compliance — varnostna dokumentacija 21. člena (predloge + placeholderji).

DETERMINISTIČNO (D1): dokumentacija NISO LLM-generirane — so predloge iz
URSIV/ENISA smernic (``rules/policies/*.md``) z zapolnjenimi placeholderji.
LLM halucinacija nima mesta v pravnem dokumentu.

Child #7 realignment: ``rules/policies/`` vsebuje 8 predlog, ki zrcalijo
8 dokumentov 21(1) (politike → ``legal_ref`` na 21. člen (1) N. točko).
Oba tier-ja dobita vseh 8 dokumentov (ZInfV-1 21(1) velja za oba); vsebina je
tier-parametrizirana (bistveni: poln BCP + strožji pragovi; pomembni: mehkejši).
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings  # noqa: E402
from actions.nis2_compliance.schemas import (  # noqa: E402
    FirmProfile,
    LegalRef,
    PolicyDoc,
    PolicyNotFoundError,
    PolicyRenderError,
    ScopeResult,
)

#: ``{{placeholder}}`` sintaksa (črke/števke/podčrtaj).
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
#: Zaznava nedorečenih placeholderjev po substituciji (AC: output brez ``{{``).
_ANY_PLACEHOLDER_RE = re.compile(r"\{\{.*?\}\}")


class PolicyTemplate:
    """Markdown predloga + placeholderji. Deterministično, brez LLM."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.policy_id = self.path.stem
        self.source = self.path.read_text(encoding="utf-8")


#: policy_id (ime datoteke brez .md) → človeški naslov dokumenta (21. člen).
POLICY_TITLES: dict[str, str] = {
    "informacijska-varnostna-politika": "Informacijska varnostna politika",
    "popis-sredstev": "Popis informacijskih sredstev in upravljavcev",
    "upravljanje-tveganj": "Analiza obvladovanja tveganj",
    "bcp": "Politika in načrt neprekinjenega poslovanja",
    "nacrt-obnovitve": "Načrt obnovitve in ponovne vzpostavitve delovanja",
    "incident-handling": "Načrt odzivanja na incidente",
    "nacrt-varnostnih-ukrepov": "Načrt varnostnih ukrepov (CIA)",
    "presoja-ucinkovitosti": "Politika presoje učinkovitosti varnostnih ukrepov",
}

#: policy_id → 21. člen (1) N. točka (8 dokumentov). Single source za legal_ref.
POLICY_DOC_TOCKA: dict[str, int] = {
    "informacijska-varnostna-politika": 1,
    "popis-sredstev": 2,
    "upravljanje-tveganj": 3,
    "bcp": 4,
    "nacrt-obnovitve": 5,
    "incident-handling": 6,
    "nacrt-varnostnih-ukrepov": 7,
    "presoja-ucinkovitosti": 8,
}


def _now() -> int:
    return int(time.time())


def _tier_substitutions(scope: ScopeResult) -> dict[str, str]:
    """Tier-prilagojena vsebina: bistveni = poln BCP + strožji pragovi."""
    if scope.tier == "bistveni":
        return {
            "bcp_scope": (
                "Poln načrt neprekinjenosti poslovanja z obnovitvenimi cilji "
                "(RTO/RPO), kriznim upravljanjem in rednimi vajami obnove."
            ),
            "supply_chain_scope": (
                "Formalna ocena varnosti ključnih dobaviteljev, pogodbene "
                "varnostne zahteve in redne revizije dobavne verige."
            ),
            "access_policy_note": (
                "Strogi nadzor dostopa z načelom najmanjših pravic in "
                "obvezno večfaktorsko avtentikacijo (MFA) za oddaljeni dostop "
                "in privilegirane račune."
            ),
        }
    if scope.tier == "pomembni":
        return {
            "bcp_scope": (
                "Osnovni postopki varnostnega kopiranja in obnove ključnih "
                "sistemov ter poenostavljen načrt neprekinjenosti poslovanja "
                "z mehkejšimi roki."
            ),
            "supply_chain_scope": (
                "Pregled ključnih dobaviteljev z lažjimi (best-effort) "
                "varnostnimi zahtevami brez formalnih revizij."
            ),
            "access_policy_note": (
                "Nadzor dostopa z osnovnimi pravicami in MFA, kjer je "
                "tehnično mogoče."
            ),
        }
    return {
        "bcp_scope": "Osnovni postopki varnostnega kopiranja.",
        "supply_chain_scope": "Pregled ključnih dobaviteljev.",
        "access_policy_note": "Osnovni nadzor dostopa.",
    }


def _substitution_map(firm: FirmProfile, scope: ScopeResult) -> dict[str, str]:
    """Celoten placeholder → vrednost preslikava za renderiranje."""
    mapping: dict[str, str] = {
        "firma_naziv": firm.naziv,
        "sektor": firm.sektor,
        "kontakt": firm.kontakt or "direktor",
        "tier": scope.tier,
        "zaposleni": str(firm.zaposleni),
        "promet_mio": f"{firm.promet_mio:g}",
        "deadline": settings.nis2_deadline,
        "incident_early_warning_h": "24",
        "incident_assessment_h": "72",
        "incident_final_report_d": "30",
    }
    mapping.update(_tier_substitutions(scope))
    return mapping


def _substitute(source: str, mapping: dict[str, str]) -> str:
    def _repl(match: re.Match) -> str:
        key = match.group(1)
        if key not in mapping:
            raise PolicyRenderError(f"neznan placeholder: {{{{{key}}}}}")
        return mapping[key]

    return _PLACEHOLDER_RE.sub(_repl, source)


def render_policy(
    template: Path,
    firm: FirmProfile,
    scope: ScopeResult,
    rendered_at: int | None = None,
) -> PolicyDoc:
    """Substituira placeholderje ({{firma_naziv}}, {{sektor}}, {{tier}}, ...).

    DETERMINISTIČNO: isti vhod → isti output. Ne-substituiran placeholder →
    PolicyRenderError (output nikoli nima nedorečenih placeholderjev).
    ``legal_ref`` se izpelje iz ``POLICY_DOC_TOCKA`` (21. člen (1) N. točka).
    """
    if not Path(template).is_file():
        raise PolicyNotFoundError(f"Predloga ne obstaja: {template}")
    tpl = PolicyTemplate(template)
    body = _substitute(tpl.source, _substitution_map(firm, scope))
    remaining = _ANY_PLACEHOLDER_RE.findall(body)
    if remaining:
        raise PolicyRenderError(f"ne-substituiran placeholder: {remaining[0]}")
    tocka = POLICY_DOC_TOCKA.get(tpl.policy_id)
    if tocka is None:
        raise PolicyNotFoundError(
            f"Predloga ni mapirana na 21. člen (1) dokumentacijo: {tpl.policy_id}"
        )
    title = POLICY_TITLES.get(tpl.policy_id, tpl.policy_id)
    return PolicyDoc(
        policy_id=tpl.policy_id,
        title=title,
        legal_ref=LegalRef(clen=21, odstavek=1, tocka=tocka),
        body_markdown=body,
        rendered_at=int(rendered_at) if rendered_at is not None else _now(),
    )


def render_all_policies(
    templates_dir: Path,
    firm: FirmProfile,
    scope: ScopeResult,
    rendered_at: int | None = None,
) -> list[PolicyDoc]:
    """Renderira vse predloge (*.md) v imeniku — OBA tier-ja dobita vseh 8."""
    docs: list[PolicyDoc] = []
    for tpl_path in sorted(Path(templates_dir).glob("*.md")):
        docs.append(render_policy(tpl_path, firm, scope, rendered_at))
    return docs


def build_user_notice(
    firm: FirmProfile,
    scope: ScopeResult,
    incident_opis: str = "Pomemben varnostni incident",
    rendered_at: int | None = None,
) -> PolicyDoc:
    """Predloga obvestila uporabnikom storitev (ZInfV-1 29(6)) z ukrepi (29(7)).

    Ko pomemben incident verjetno negativno vpliva na zagotavljanje storitev,
    mora subjekt uporabnike nemudoma obvestiti (29(6)) in jim sporočiti ukrepe,
    ki jih lahko sprejmejo v odziv na grožnjo (29(7)).
    """
    m = _substitution_map(firm, scope)
    body = (
        "# Obvestilo uporabnikom storitev (ZInfV-1 29(6))\n\n"
        f"**Organizacija:** {m['firma_naziv']}\n"
        f"**Kontakt:** {m['kontakt']}\n\n"
        "## 1. Obvestilo o pomembnem incidentu\n"
        f"Organizacija {m['firma_naziv']} vas obvešča o pomembnem incidentu, ki "
        f"verjetno negativno vpliva na zagotavljanje naših storitev:\n\n"
        f"> {incident_opis}\n\n"
        "## 2. Ukrepi, ki jih lahko uporabniki sprejmejo (ZInfV-1 29(7))\n"
        "- Spremljajte uradna obvestila organizacije za nadaljnje informacije.\n"
        "- Ob morebitni zlorabi poverilnic jih takoj zamenjajte.\n"
        "- Bodite pozorni na lažna (phishing) sporočila, ki se sklicujejo na ta incident.\n"
        "- O sumljivih aktivnostih obvestite kontakt: " + m["kontakt"] + ".\n\n"
        "_Predloga obvestila uporabnikom storitev — ZInfV-1 29(6) in (7)._\n"
    )
    return PolicyDoc(
        policy_id="obvestilo-uporabnikom",
        title="Obvestilo uporabnikom storitev (ZInfV-1 29(6))",
        legal_ref=LegalRef(clen=29, odstavek=6, tocka=None),
        body_markdown=body,
        rendered_at=int(rendered_at) if rendered_at is not None else _now(),
    )
