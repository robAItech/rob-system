"""nis2_compliance — testi obseg determinacije (child #2, E6, vse offline)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings  # noqa: E402
from actions.nis2_compliance.schemas import (  # noqa: E402
    InvalidScopeInputError,
    ScopeInput,
)
from actions.nis2_compliance.scope import determine_scope  # noqa: E402

THRESHOLDS = {
    "zaposleni": {"pomembni": 50, "bistveni": 250},
    "promet_mio": {"pomembni": 10, "bistveni": 50},
}
PRILOGA = {
    "priloga1": ["energetika", "transport", "zdravstvo"],
    "priloga2": ["kemikalije", "hrana", "proizvodnja"],
}


def _input(zaposleni=40, promet=8.0, sektor="storitve") -> ScopeInput:
    # "storitve" ni v nobeni prilogi → velikostne meje odločijo (ne sektor).
    return ScopeInput(zaposleni=zaposleni, promet_mio=promet, sektor=sektor)


def test_bistveni_velikost():
    """zaposleni=300 → bistveni (meja ≥250)."""
    res = determine_scope(_input(zaposleni=300, promet=8.0), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"
    assert "250" in res.razlog and "bistveni" in res.razlog


def test_bistveni_promet():
    """promet=100 ≥ 50 → bistveni (meja ≥50)."""
    res = determine_scope(_input(zaposleni=60, promet=100.0), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"
    assert "50" in res.razlog


def test_pomembni_velikost():
    """zaposleni=60, promet=12 → pomembni (≥50 in ≥10)."""
    res = determine_scope(_input(zaposleni=60, promet=12.0), THRESHOLDS, PRILOGA)
    assert res.tier == "pomembni"
    assert "50" in res.razlog and "10" in res.razlog


def test_izven():
    """zaposleni=40, promet=8 → izven (review gate: razlog imenuje meje)."""
    res = determine_scope(_input(zaposleni=40, promet=8.0), THRESHOLDS, PRILOGA)
    assert res.tier == "izven"
    assert "50" in res.razlog and "10" in res.razlog


def test_priloga1_bistveni():
    """sektor v Priloga 1 → bistveni ne glede na velikost."""
    res = determine_scope(_input(zaposleni=10, promet=1.0, sektor="zdravstvo"), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"
    assert "Priloga 1" in res.razlog


def test_priloga2_pomembni():
    """sektor v Priloga 2 → pomembni ne glede na velikost."""
    res = determine_scope(_input(zaposleni=10, promet=1.0, sektor="kemikalije"), THRESHOLDS, PRILOGA)
    assert res.tier == "pomembni"
    assert "Priloga 2" in res.razlog


def test_negativen_vhod_zaposleni():
    with pytest.raises(InvalidScopeInputError):
        determine_scope(_input(zaposleni=-1), THRESHOLDS, PRILOGA)


def test_negativen_vhod_promet():
    with pytest.raises(InvalidScopeInputError):
        determine_scope(_input(promet=-5.0), THRESHOLDS, PRILOGA)


def test_sektor_normaliziran():
    """Vhodni sektor se normalizira (case/whitespace)."""
    res = determine_scope(
        _input(zaposleni=10, promet=1.0, sektor="  Zdravstvo  "), THRESHOLDS, PRILOGA
    )
    assert res.tier == "bistveni"


def test_config_driven_monkeypatch():
    """AC5: spremenjene meje (monkeypatch settings) spremenijo rezultat brez kode."""
    modified = {
        "zaposleni": {"pomembni": 30, "bistveni": 250},
        "promet_mio": {"pomembni": 5, "bistveni": 50},
    }
    # S privzetimi mejami bi bilo "izven"; z novimi → "pomembni".
    res = determine_scope(_input(zaposleni=35, promet=6.0), modified, PRILOGA)
    assert res.tier == "pomembni"
    # Dokaz, da settings objekt dejansko vsebuje privzete meje (config-driven).
    assert settings.nis2_scope_thresholds["zaposleni"]["pomembni"] == 50


def test_evidence_includes_used_thresholds():
    """AC5: evidence vsebuje input vrednosti + uporabljene meje (review gate)."""
    res = determine_scope(_input(zaposleni=300, promet=8.0), THRESHOLDS, PRILOGA)
    assert res.evidence["input"]["zaposleni"] == 300
    meje = res.evidence["uporabljene_meje"]
    assert meje["zaposleni"]["bistveni"] == 250
    assert meje["promet_mio"]["pomembni"] == 10
