"""nis2_compliance — obseg determinacija (E6, child #2).

Deterministično preslika vprašalnik (zaposleni/promet/sektor) v
bistveni / pomembni / izven po ZInfV-1 6./7. členu. Meje so config-driven
(``NIS2_SCOPE_THRESHOLDS``), sektorji po prilogah (``NIS2_PRILOGA_SECTORS``).

Pravilo (ZInfV-1 6./7. člen):
- sektor v Priloga 1 → bistveni (ne glede na velikost pri določenih)
- sektor v Priloga 2 → pomembni (ne glede na velikost pri določenih)
- zaposleni >= bistveni OR promet >= bistveni → bistveni
- zaposleni >= pomembni AND promet >= pomembni → pomembni
- sicer → izven obsega

"izven" zahteva dodatni review gate (I3): ``razlog`` vsebuje reference na
uporabljene meje, da lahko človek preveri.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from actions.nis2_compliance.schemas import (  # noqa: E402
    InvalidScopeInputError,
    ScopeInput,
    ScopeResult,
)


def _now() -> int:
    return int(time.time())


def _evidence(
    input: ScopeInput, thresholds: dict, z_p: int, z_b: int, p_p: float, p_b: float
) -> dict[str, Any]:
    return {
        "input": {
            "zaposleni": input.zaposleni,
            "promet_mio": input.promet_mio,
            "sektor": input.sektor,
        },
        "uporabljene_meje": {
            "zaposleni": {"pomembni": z_p, "bistveni": z_b},
            "promet_mio": {"pomembni": p_p, "bistveni": p_b},
        },
    }


def determine_scope(input: ScopeInput, thresholds: dict, priloga: dict) -> ScopeResult:
    """Deterministično: bistveni / pomembni / izven.

    Raises:
        InvalidScopeInputError: negativen zaposleni ali promet (fail-loud).
    """
    if input.zaposleni < 0:
        raise InvalidScopeInputError(f"negativen zaposleni: {input.zaposleni}")
    if input.promet_mio < 0:
        raise InvalidScopeInputError(f"negativen promet: {input.promet_mio}")

    sektor = input.sektor.strip().lower()
    priloga1 = {str(s).strip().lower() for s in priloga.get("priloga1", [])}
    priloga2 = {str(s).strip().lower() for s in priloga.get("priloga2", [])}

    z_bistveni = int(thresholds["zaposleni"]["bistveni"])
    z_pomembni = int(thresholds["zaposleni"]["pomembni"])
    p_bistveni = float(thresholds["promet_mio"]["bistveni"])
    p_pomembni = float(thresholds["promet_mio"]["pomembni"])

    if sektor in priloga1:
        return ScopeResult(
            tier="bistveni",
            razlog=f"sektor '{input.sektor}' v Priloga 1 → bistveni",
            evidence=_evidence(input, thresholds, z_pomembni, z_bistveni, p_pomembni, p_bistveni),
            checked_at=_now(),
        )
    if sektor in priloga2:
        return ScopeResult(
            tier="pomembni",
            razlog=f"sektor '{input.sektor}' v Priloga 2 → pomembni",
            evidence=_evidence(input, thresholds, z_pomembni, z_bistveni, p_pomembni, p_bistveni),
            checked_at=_now(),
        )

    if input.zaposleni >= z_bistveni or input.promet_mio >= p_bistveni:
        if input.zaposleni >= z_bistveni and input.promet_mio >= p_bistveni:
            razlog = (
                f"zaposleni={input.zaposleni} ≥ {z_bistveni} in "
                f"promet={input.promet_mio} ≥ {p_bistveni} (bistveni)"
            )
        elif input.zaposleni >= z_bistveni:
            razlog = f"zaposleni={input.zaposleni} ≥ {z_bistveni} (bistveni)"
        else:
            razlog = f"promet={input.promet_mio} ≥ {p_bistveni} (bistveni)"
        return ScopeResult(
            tier="bistveni",
            razlog=razlog,
            evidence=_evidence(input, thresholds, z_pomembni, z_bistveni, p_pomembni, p_bistveni),
            checked_at=_now(),
        )

    if input.zaposleni >= z_pomembni and input.promet_mio >= p_pomembni:
        razlog = (
            f"zaposleni={input.zaposleni} ≥ {z_pomembni} in "
            f"promet={input.promet_mio} ≥ {p_pomembni} (pomembni)"
        )
        return ScopeResult(
            tier="pomembni",
            razlog=razlog,
            evidence=_evidence(input, thresholds, z_pomembni, z_bistveni, p_pomembni, p_bistveni),
            checked_at=_now(),
        )

    razlog = (
        f"pod mejo: zaposleni={input.zaposleni} < {z_pomembni} ali "
        f"promet={input.promet_mio} < {p_pomembni}"
    )
    return ScopeResult(
        tier="izven",
        razlog=razlog,
        evidence=_evidence(input, thresholds, z_pomembni, z_bistveni, p_pomembni, p_bistveni),
        checked_at=_now(),
    )
