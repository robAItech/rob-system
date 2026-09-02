"""nis2_compliance — obseg determinacija (E6, child #2 + #7 realignment).

Deterministično preslika vprašalnik (zaposleni/promet/bilančna/sektor/kategorija)
v bistveni / pomembni / izven po ZInfV-1 6./7. členu. Meje so config-driven
(``NIS2_SCOPE_THRESHOLDS``), sektorji po prilogah (``rules/zinfv1_priloge.json``).

Pravilo po realignmentu (child #7 — pravna logika namesto NIS2 poenostavitve):

- **posebna kategorija** (``kategorija="posebna"``: DNS, TLD, kvalificirane
  storitve zaupanja, državna uprava) → bistveni ne glede na velikost (7(2));
- **Priloga 1** (visoko kritični): 250 zap. ALI 50M€ prometa ALI 43M€ bilančne
  vsote → bistveni; sicer 50 zap. IN (10M€ prometa ALI 10M€ bilančne) → pomembni;
- **Priloga 2** (drugi kritični): 50 zap. IN (10M€ prometa ALI 10M€ bilančne)
  → pomembni;
- **neznan/drug sektor**: velikostna logika brez sektorskega pogoja (AC7).

"izven" zahteva dodatni review gate (I3): ``razlog`` vsebuje reference na
uporabljene meje, da lahko človek preveri.
"""

from __future__ import annotations

import json
import os
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

PRILOGE_FILENAME = "zinfv1_priloge.json"


def _now() -> int:
    return int(time.time())


def _default_rules_dir() -> Path:
    env = os.environ.get("NIS2_RULES_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "rules"


def load_priloge(path: Path | None = None) -> dict[str, list[str]]:
    """Naloži ``zinfv1_priloge.json`` → ``{"priloga1": [...], "priloga2": [...]}``.

    Normalizira obe možni obliki (seznam slugov ali ``{"sectors": [...]}``) na
    seznam slugov, da je potrošnik (determine_scope) enoten.
    """
    priloge_path = (Path(path) if path is not None else _default_rules_dir()) / PRILOGE_FILENAME
    if not priloge_path.is_file():
        raise FileNotFoundError(f"Priloge datoteka ne obstaja: {priloge_path}")
    data = json.loads(priloge_path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for key in ("priloga1", "priloga2"):
        raw = data.get(key, [])
        if isinstance(raw, dict):
            out[key] = list(raw.get("sectors", []))
        else:
            out[key] = list(raw)
    return out


def _sector_list(priloga: dict, key: str) -> set[str]:
    raw = priloga.get(key, []) if isinstance(priloga, dict) else []
    if isinstance(raw, dict):
        raw = raw.get("sectors", [])
    return {str(s).strip().lower() for s in raw}


def _za_zavezanec(zaposleni: int, promet: float, bilancna: float, z_p: int, p_p: float, b_p: float) -> bool:
    """Prag zavezanca (pomembni): 50 zap. IN (promet ALI bilančna ≥ 10M)."""
    return zaposleni >= z_p and (promet >= p_p or bilancna >= b_p)


def _threshold_flags(
    scope_input: ScopeInput, z_b: int, p_b: float, b_b: float
) -> list[str]:
    """Opisi izpolnjenih bistvenih mej — za razlog (review gate)."""
    flags: list[str] = []
    if scope_input.zaposleni >= z_b:
        flags.append(f"zaposleni={scope_input.zaposleni} ≥ {z_b}")
    if scope_input.promet_mio >= p_b:
        flags.append(f"promet={scope_input.promet_mio} ≥ {p_b}")
    if scope_input.bilancna_vsota_mio >= b_b:
        flags.append(f"bilancna_vsota={scope_input.bilancna_vsota_mio} ≥ {b_b}")
    return flags


def _evidence(
    scope_input: ScopeInput, thresholds: dict, z_p: int, z_b: int, p_p: float, p_b: float, b_p: float, b_b: float
) -> dict[str, Any]:
    return {
        "input": {
            "zaposleni": scope_input.zaposleni,
            "promet_mio": scope_input.promet_mio,
            "bilancna_vsota_mio": scope_input.bilancna_vsota_mio,
            "sektor": scope_input.sektor,
            "kategorija": scope_input.kategorija,
        },
        "uporabljene_meje": {
            "zaposleni": {"pomembni": z_p, "bistveni": z_b},
            "promet_mio": {"pomembni": p_p, "bistveni": p_b},
            "bilancna_vsota_mio": {"pomembni": b_p, "bistveni": b_b},
        },
    }


def determine_scope(scope_input: ScopeInput, thresholds: dict, priloga: dict) -> ScopeResult:
    """Deterministično: bistveni / pomembni / izven.

    Raises:
        InvalidScopeInputError: negativen zaposleni/promet/bilančna (fail-loud).
    """
    if scope_input.zaposleni < 0:
        raise InvalidScopeInputError(f"negativen zaposleni: {scope_input.zaposleni}")
    if scope_input.promet_mio < 0:
        raise InvalidScopeInputError(f"negativen promet: {scope_input.promet_mio}")
    if scope_input.bilancna_vsota_mio < 0:
        raise InvalidScopeInputError(f"negativna bilancna vsota: {scope_input.bilancna_vsota_mio}")

    sektor = scope_input.sektor.strip().lower()
    priloga1 = _sector_list(priloga, "priloga1")
    priloga2 = _sector_list(priloga, "priloga2")

    z_bistveni = int(thresholds["zaposleni"]["bistveni"])
    z_pomembni = int(thresholds["zaposleni"]["pomembni"])
    p_bistveni = float(thresholds["promet_mio"]["bistveni"])
    p_pomembni = float(thresholds["promet_mio"]["pomembni"])
    b_bistveni = float(thresholds["bilancna_vsota_mio"]["bistveni"])
    b_pomembni = float(thresholds["bilancna_vsota_mio"]["pomembni"])

    evidence = _evidence(
        scope_input, thresholds, z_pomembni, z_bistveni, p_pomembni, p_bistveni, b_pomembni, b_bistveni
    )

    # Posebna kategorija (7(2) 2.–4. t.): bistveni ne glede na velikost.
    if scope_input.kategorija == "posebna":
        return ScopeResult(
            tier="bistveni",
            razlog=(
                f"posebna kategorija ('{scope_input.sektor}') → bistveni "
                f"ne glede na velikost (ZInfV-1 7(2))"
            ),
            evidence=evidence,
            checked_at=_now(),
        )

    # Priloga 1 — bistveni ob 250/50M€/43M€ OR; pod pragom a ≥50/10M€ → pomembni.
    if sektor in priloga1:
        flags = _threshold_flags(scope_input, z_bistveni, p_bistveni, b_bistveni)
        if flags:
            return ScopeResult(
                tier="bistveni",
                razlog=f"sektor '{scope_input.sektor}' v Prilogi 1 in {', '.join(flags)} (bistveni)",
                evidence=evidence,
                checked_at=_now(),
            )
        if _za_zavezanec(scope_input.zaposleni, scope_input.promet_mio, scope_input.bilancna_vsota_mio, z_pomembni, p_pomembni, b_pomembni):
            return ScopeResult(
                tier="pomembni",
                razlog=(
                    f"sektor '{scope_input.sektor}' v Prilogi 1 pod bistvenim pragom; "
                    f"zaposleni={scope_input.zaposleni} ≥ {z_pomembni} in "
                    f"(promet={scope_input.promet_mio} ≥ {p_pomembni} ali "
                    f"bilancna={scope_input.bilancna_vsota_mio} ≥ {b_pomembni}) (pomembni)"
                ),
                evidence=evidence,
                checked_at=_now(),
            )
        return ScopeResult(
            tier="izven",
            razlog=(
                f"sektor '{scope_input.sektor}' v Prilogi 1, a pod pragom: "
                f"zaposleni={scope_input.zaposleni} < {z_pomembni} ali "
                f"(promet={scope_input.promet_mio} < {p_pomembni} in "
                f"bilancna={scope_input.bilancna_vsota_mio} < {b_pomembni})"
            ),
            evidence=evidence,
            checked_at=_now(),
        )

    # Priloga 2 — pomembni ob 50 IN (10M€ prometa ALI 10M€ bilančne).
    if sektor in priloga2:
        if _za_zavezanec(scope_input.zaposleni, scope_input.promet_mio, scope_input.bilancna_vsota_mio, z_pomembni, p_pomembni, b_pomembni):
            return ScopeResult(
                tier="pomembni",
                razlog=(
                    f"sektor '{scope_input.sektor}' v Prilogi 2 in "
                    f"zaposleni={scope_input.zaposleni} ≥ {z_pomembni} in "
                    f"(promet={scope_input.promet_mio} ≥ {p_pomembni} ali "
                    f"bilancna={scope_input.bilancna_vsota_mio} ≥ {b_pomembni}) (pomembni)"
                ),
                evidence=evidence,
                checked_at=_now(),
            )
        return ScopeResult(
            tier="izven",
            razlog=(
                f"sektor '{scope_input.sektor}' v Prilogi 2, a pod pragom: "
                f"zaposleni={scope_input.zaposleni} < {z_pomembni} ali "
                f"(promet={scope_input.promet_mio} < {p_pomembni} in "
                f"bilancna={scope_input.bilancna_vsota_mio} < {b_pomembni})"
            ),
            evidence=evidence,
            checked_at=_now(),
        )

    # Neznan/drug sektor → velikostna logika brez sektorskega pogoja (AC7).
    flags = _threshold_flags(scope_input, z_bistveni, p_bistveni, b_bistveni)
    if flags:
        razlog = ", ".join(flags) + " (bistveni)"
        return ScopeResult(tier="bistveni", razlog=razlog, evidence=evidence, checked_at=_now())
    if _za_zavezanec(scope_input.zaposleni, scope_input.promet_mio, scope_input.bilancna_vsota_mio, z_pomembni, p_pomembni, b_pomembni):
        razlog = (
            f"zaposleni={scope_input.zaposleni} ≥ {z_pomembni} in "
            f"(promet={scope_input.promet_mio} ≥ {p_pomembni} ali "
            f"bilancna={scope_input.bilancna_vsota_mio} ≥ {b_pomembni}) (pomembni)"
        )
        return ScopeResult(tier="pomembni", razlog=razlog, evidence=evidence, checked_at=_now())
    razlog = (
        f"pod mejo: zaposleni={scope_input.zaposleni} < {z_pomembni} ali "
        f"(promet={scope_input.promet_mio} < {p_pomembni} in "
        f"bilancna={scope_input.bilancna_vsota_mio} < {b_pomembni})"
    )
    return ScopeResult(tier="izven", razlog=razlog, evidence=evidence, checked_at=_now())
