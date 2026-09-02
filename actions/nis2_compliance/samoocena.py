"""nis2_compliance — samoocena skladnosti (ZInfV-1 25. člen, child #7).

Izroček za pomembne subjekte (in podatki za revizorja pri bistvenih):

- **pomembni** (25(3)): dokumentirana samoocena skladnosti z varnostno
  dokumentacijo (21. člen) in izvajanjem ukrepov (22. člen) → če so vse
  postavke "dokazano"/"potrjeno": **izjava o skladnosti** (25(4)); sicer
  **izjava o ugotavljanju neskladnosti** z načrtom odprave in roki (25(5)).
- **bistveni** (25(1)): ocena skladnosti se izvede kot revizija — ni
  generativno; modul pripravi **revizijski paket** (podatki za revizorja).

Frekvenca: najmanj enkrat na dve leti ali ob pomembnem incidentu.
Deterministično, brez LLM.
"""

from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.rules_engine import get_obligations  # noqa: E402
from actions.nis2_compliance.schemas import (  # noqa: E402
    EvidenceDraft,
    FirmProfile,
    OdpravaNacrt,
    RulesBundle,
    SamoocenaError,
    SamoocenaIzjava,
    SamoocenaReport,
    SamoocenaUgotovitev,
    ScopeResult,
)

#: Statusa, ki v samooceni štejeta kot skladno (ostala → neskladnost).
SKLADNO_STATUSI = ("dokazano", "potrjeno")

#: Privzeti rok za odpravo ugotovljenih neskladnosti (25(5)).
ODPRAVA_ROK_DNI = 90


def _now() -> int:
    return int(time.time())


def _rok_iso(ocenjeno_at: int, dni: int) -> str:
    """ISO datum za rok odprave = datum ocene + ``dni``."""
    d = datetime.fromtimestamp(ocenjeno_at).date() + timedelta(days=dni)
    return d.isoformat()


def prepare_samoocena(
    firm: FirmProfile,
    scope_result: ScopeResult,
    evidence: list[EvidenceDraft],
    bundle: RulesBundle,
    now: int | None = None,
    odprava_rok_dni: int = ODPRAVA_ROK_DNI,
) -> SamoocenaReport:
    """Deterministična samoocena skladnosti (25. člen).

    Upošteva vse obveznosti tier-ja RAZEN tistih iz 25. člena (samoocena/
    revizija je izroček tega modula — ne sme ocenjevati same sebe).

    Raises:
        SamoocenaError: firma ni zavezanec (tier "izven").
    """
    ts = int(now) if now is not None else _now()
    if scope_result.tier not in ("bistveni", "pomembni"):
        raise SamoocenaError(
            f"Samoocena zahteva zavezanca (bistveni/pomembni), dobila '{scope_result.tier}'"
        )
    tier = scope_result.tier

    evidence_by_item = {e.item_id: e for e in evidence}
    obligations = [
        o for o in get_obligations(bundle, tier) if o.legal_ref.clen != 25
    ]

    items: list[SamoocenaUgotovitev] = []
    for obl in obligations:
        for item in obl.checklist:
            ev = evidence_by_item.get(item.item_id)
            status = ev.status if ev is not None else "ni začeto"
            skladno = status in SKLADNO_STATUSI
            items.append(
                SamoocenaUgotovitev(
                    obligation_id=obl.obligation_id,
                    item_id=item.item_id,
                    opis=item.description,
                    status=status,
                    skladno=skladno,
                )
            )

    skladnost = bool(items) and all(i.skladno for i in items)
    neskladni = [i for i in items if not i.skladno]

    nacrt: list[OdpravaNacrt] = []
    for i in neskladni:
        nacrt.append(
            OdpravaNacrt(
                item_id=i.item_id,
                ugotovitev=f"{i.opis} (status: {i.status})",
                ukrep=f"Vzpostaviti dokazilo in ukrepe za skladnost: {i.opis}",
                rok=_rok_iso(ts, int(odprava_rok_dni)),
            )
        )

    if tier == "pomembni":
        vrsta = "samoocena"
        if skladnost:
            izjava = SamoocenaIzjava(
                vrsta="skladnosti",
                besedilo=(
                    f"Izjava o skladnosti po ZInfV-1 25(4): {firm.naziv} izpolnjuje "
                    f"zahteve informacijske in kibernetske varnosti, predpisane s tem "
                    f"zakonom, na podlagi samoocene skladnosti z dne {date.fromtimestamp(ts).isoformat()}."
                ),
            )
        else:
            izjava = SamoocenaIzjava(
                vrsta="ugotavljanje_neskladnosti",
                besedilo=(
                    f"Izjava o ugotavljanju neskladnosti po ZInfV-1 25(5): {firm.naziv} "
                    f"ne izpolnjuje vseh predpisanih zahtev. Ugotovljenih je "
                    f"{len(neskladni)} neskladnosti; načrt odprave z roki je priložen."
                ),
            )
    else:
        vrsta = "revizijski_paket"
        izjava = None

    return SamoocenaReport(
        firm_id=firm.firm_id,
        tier=tier,
        vrsta=vrsta,
        skladnost=skladnost,
        ocenjeno_at=ts,
        items=items,
        izjava=izjava,
        nacrt_odprave=nacrt,
    )
