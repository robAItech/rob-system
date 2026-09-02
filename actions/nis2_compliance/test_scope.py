"""nis2_compliance — testi obseg determinacije (child #2 + #7 realignment, offline).

Realigned pravna logika (ZInfV-1 6./7. člen):
- Priloga 1 + 250/50M€/43M€ OR → bistveni; pod pragom a ≥50/10M€ → pomembni.
- Priloga 2 + 50 IN (10M€ prometa ALI 10M€ bilančne) → pomembni.
- Posebna kategorija → bistveni ne glede na velikost.
- Neznan sektor → velikostna logika brez sektorskega pogoja (AC7).
"""

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
from actions.nis2_compliance.scope import determine_scope, load_priloge  # noqa: E402

THRESHOLDS = {
    "zaposleni": {"pomembni": 50, "bistveni": 250},
    "promet_mio": {"pomembni": 10, "bistveni": 50},
    "bilancna_vsota_mio": {"pomembni": 10, "bistveni": 43},
}
PRILOGA = {
    "priloga1": ["energija", "promet", "zdravje"],
    "priloga2": ["proizvodnja", "hrana", "postne_storitve"],
}


def _input(zaposleni=40, promet=8.0, bilancna=0.0, sektor="storitve", kategorija="splosno") -> ScopeInput:
    # "storitve" ni v nobeni prilogi → velikostna logika (AC7 fallback).
    return ScopeInput(
        zaposleni=zaposleni, promet_mio=promet, bilancna_vsota_mio=bilancna,
        sektor=sektor, kategorija=kategorija,
    )


def test_bistveni_velikost_generic():
    """Neznan sektor: zaposleni=300 → bistveni (meja ≥250)."""
    res = determine_scope(_input(zaposleni=300, promet=8.0), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"
    assert "250" in res.razlog and "bistveni" in res.razlog


def test_bistveni_promet_generic():
    """Neznan sektor: promet=100 ≥ 50 → bistveni (meja ≥50)."""
    res = determine_scope(_input(zaposleni=60, promet=100.0), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"
    assert "50" in res.razlog


def test_pomembni_velikost_generic():
    """Neznan sektor: 60/12 → pomembni (≥50 in ≥10)."""
    res = determine_scope(_input(zaposleni=60, promet=12.0), THRESHOLDS, PRILOGA)
    assert res.tier == "pomembni"
    assert "50" in res.razlog and "10" in res.razlog


def test_izven_generic():
    """Neznan sektor: 40/8 → izven (review gate: razlog imenuje meje)."""
    res = determine_scope(_input(zaposleni=40, promet=8.0), THRESHOLDS, PRILOGA)
    assert res.tier == "izven"
    assert "50" in res.razlog and "10" in res.razlog


def test_priloga1_z_velikostnim_pragom_bistveni():
    """AC6: Priloga 1 + zaposleni≥250 → bistveni."""
    res = determine_scope(_input(zaposleni=300, promet=30.0, sektor="energija"), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"
    assert "Prilogi 1" in res.razlog or "Priloga 1" in res.razlog


def test_priloga1_brez_praga_ni_bistveni():
    """AC6: Priloga 1 brez velikostnega praga → NI avtomatsko bistveni (razen posebne)."""
    res = determine_scope(_input(zaposleni=10, promet=1.0, sektor="zdravje"), THRESHOLDS, PRILOGA)
    assert res.tier == "izven"


def test_priloga1_pod_bistvenim_nad_zavezancem_pomembni():
    """Priloga 1 pod 250/50/43, a ≥50/10 → pomembni (zavezanec, ni bistveni)."""
    res = determine_scope(_input(zaposleni=200, promet=30.0, bilancna=30.0, sektor="energija"), THRESHOLDS, PRILOGA)
    assert res.tier == "pomembni"
    assert "pomembni" in res.razlog


def test_priloga2_prag_pomembni():
    """AC6: Priloga 2 + 60/12 → pomembni."""
    res = determine_scope(_input(zaposleni=60, promet=12.0, sektor="proizvodnja"), THRESHOLDS, PRILOGA)
    assert res.tier == "pomembni"
    assert "Priloga 2" in res.razlog or "Prilogi 2" in res.razlog


def test_priloga2_pod_pragom_izven():
    """Priloga 2 pod pragom (10/1) → izven (ni več avtomatsko pomembni)."""
    res = determine_scope(_input(zaposleni=10, promet=1.0, sektor="proizvodnja"), THRESHOLDS, PRILOGA)
    assert res.tier == "izven"


def test_posebna_kategorija_bistveni_ne_glede_na_velikost():
    """AC6: kategorija='posebna' → bistveni ne glede na velikost."""
    res = determine_scope(
        _input(zaposleni=5, promet=0.5, sektor="digitalna_infrastruktura", kategorija="posebna"),
        THRESHOLDS, PRILOGA,
    )
    assert res.tier == "bistveni"
    assert "posebna" in res.razlog


def test_bilancna_vsota_decides_bistveni():
    """AC5: 200 zap + 30M€ prometa + 60M€ bilančne → bistveni (bilančna ≥ 43M€)."""
    res = determine_scope(_input(zaposleni=200, promet=30.0, bilancna=60.0, sektor="energija"), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"
    assert "bilancna" in res.razlog and "43" in res.razlog
    assert res.evidence["input"]["bilancna_vsota_mio"] == 60.0
    assert res.evidence["uporabljene_meje"]["bilancna_vsota_mio"]["bistveni"] == 43


def test_bilancna_boundary_43_vs_42_99():
    """Edge: bilancna 43.0 → bistveni; 42.99 → pomembni (bilančna OR meja)."""
    bistveni = determine_scope(_input(zaposleni=200, promet=30.0, bilancna=43.0, sektor="energija"), THRESHOLDS, PRILOGA)
    assert bistveni.tier == "bistveni"
    pomembni = determine_scope(_input(zaposleni=200, promet=30.0, bilancna=42.99, sektor="energija"), THRESHOLDS, PRILOGA)
    assert pomembni.tier == "pomembni"


def test_300_30_60_bistveni_ac5():
    """AC5 spec primer: 300 zap + 30M€ prometa + 60M€ bilančne → bistveni."""
    res = determine_scope(_input(zaposleni=300, promet=30.0, bilancna=60.0, sektor="energija"), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"


def test_negativen_vhod_zaposleni():
    with pytest.raises(InvalidScopeInputError):
        determine_scope(_input(zaposleni=-1), THRESHOLDS, PRILOGA)


def test_negativen_vhod_promet():
    """Field ge=0 na ScopeInput zavrne negativen promet na robu (Pydantic)."""
    with pytest.raises(Exception):
        ScopeInput(zaposleni=60, promet_mio=-5.0, sektor="x")


def test_negativna_bilancna_vsota():
    """Field ge=0 na ScopeInput zavrne negativno bilančno vsoto na robu."""
    with pytest.raises(Exception):
        ScopeInput(zaposleni=60, promet_mio=10.0, bilancna_vsota_mio=-1.0, sektor="x")


def test_sektor_normaliziran():
    """Vhodni sektor se normalizira (case/whitespace)."""
    res = determine_scope(
        _input(zaposleni=300, promet=30.0, bilancna=60.0, sektor="  Energija  "), THRESHOLDS, PRILOGA
    )
    assert res.tier == "bistveni"


def test_config_driven_monkeypatch():
    """AC5: spremenjene meje (monkeypatch settings) spremenijo rezultat brez kode."""
    modified = {
        "zaposleni": {"pomembni": 30, "bistveni": 250},
        "promet_mio": {"pomembni": 5, "bistveni": 50},
        "bilancna_vsota_mio": {"pomembni": 5, "bistveni": 43},
    }
    # S privzetimi mejami bi bilo "izven"; z novimi → "pomembni".
    res = determine_scope(_input(zaposleni=35, promet=6.0), modified, PRILOGA)
    assert res.tier == "pomembni"
    # Dokaz, da settings objekt dejansko vsebuje bilančno mejo (config-driven).
    assert settings.nis2_scope_thresholds["zaposleni"]["pomembni"] == 50
    assert settings.nis2_scope_thresholds["bilancna_vsota_mio"]["bistveni"] == 43


def test_evidence_includes_used_thresholds():
    """AC5: evidence vsebuje input vrednosti + uporabljene meje (tudi bilančno)."""
    res = determine_scope(_input(zaposleni=300, promet=8.0), THRESHOLDS, PRILOGA)
    assert res.evidence["input"]["zaposleni"] == 300
    meje = res.evidence["uporabljene_meje"]
    assert meje["zaposleni"]["bistveni"] == 250
    assert meje["promet_mio"]["pomembni"] == 10
    assert meje["bilancna_vsota_mio"]["bistveni"] == 43


def test_obe_meji_bistveni_razlog():
    """Obe meji (zaposleni≥250 IN promet≥50) → 'bistveni' z razlogom, ki imenuje obe."""
    res = determine_scope(_input(zaposleni=300, promet=60.0), THRESHOLDS, PRILOGA)
    assert res.tier == "bistveni"
    assert "zaposleni" in res.razlog and "promet" in res.razlog


def test_scope_exact_boundaries():
    """Boundary equality: 250→bistveni, promet 50→bistveni, 50/10→pomembni, 49.99→izven."""
    assert determine_scope(_input(zaposleni=250, promet=1.0), THRESHOLDS, PRILOGA).tier == "bistveni"
    assert determine_scope(_input(zaposleni=10, promet=50.0), THRESHOLDS, PRILOGA).tier == "bistveni"
    assert determine_scope(_input(zaposleni=50, promet=10.0), THRESHOLDS, PRILOGA).tier == "pomembni"
    assert determine_scope(_input(zaposleni=50, promet=9.99), THRESHOLDS, PRILOGA).tier == "izven"


# ── Priloga data (AC7: 19 sektorjev) ─────────────────────────────────
def test_priloga_data_has_19_sectors():
    """AC7: zinfv1_priloge.json vsebuje 11 + 8 sektorjev."""
    priloge = load_priloge()
    p1 = set(priloge["priloga1"])
    p2 = set(priloge["priloga2"])
    assert len(p1) == 11
    assert len(p2) == 8
    assert len(p1 & p2) == 0
    # Reprezentativni vzorci iz uradnih prilog.
    assert {"energija", "zdravje", "digitalna_infrastruktura", "javna_uprava", "vesolje"} <= p1
    assert {"proizvodnja", "digitalni_ponudniki", "raziskave", "javna_uprava_lokalna"} <= p2


def test_unknown_sector_uses_generic_size_logic():
    """AC7: neznan sektor → velikostna logika brez sektorskega pogoja."""
    assert determine_scope(_input(zaposleni=300, sektor="storitve"), THRESHOLDS, PRILOGA).tier == "bistveni"
    assert determine_scope(_input(zaposleni=60, promet=12.0, sektor="storitve"), THRESHOLDS, PRILOGA).tier == "pomembni"
    assert determine_scope(_input(zaposleni=10, sektor="storitve"), THRESHOLDS, PRILOGA).tier == "izven"


# ── NaN/Inf zaščita (security CRITICAL fix, ship audit) ───────────────
def test_scope_input_rejects_nan():
    """NaN bilančna/promet → Pydantic zavrne (allow_inf_nan=False)."""
    with pytest.raises(Exception):
        ScopeInput(zaposleni=60, promet_mio=float("nan"), bilancna_vsota_mio=10.0, sektor="x")
    with pytest.raises(Exception):
        ScopeInput(zaposleni=60, promet_mio=10.0, bilancna_vsota_mio=float("inf"), sektor="x")


def test_scope_real_priloga_dict_form():
    """Realna priloga data (dict form {'sectors':[...]}) → sektorski izid."""
    priloge = load_priloge()  # realna rules/zinfv1_priloge.json
    # 'energija' v realni Prilogi 1 + 300/60 → bistveni.
    res = determine_scope(_input(zaposleni=300, promet=60.0, sektor="energija"), THRESHOLDS, priloge)
    assert res.tier == "bistveni"
    # 'energija' v realni Prilogi 1, a pod pragom (40/8) → NI avto-bistveni.
    res2 = determine_scope(_input(zaposleni=40, promet=8.0, sektor="energija"), THRESHOLDS, priloge)
    assert res2.tier == "izven"
    # 'proizvodnja' v realni Prilogi 2 + 60/12 → pomembni.
    res3 = determine_scope(_input(zaposleni=60, promet=12.0, sektor="proizvodnja"), THRESHOLDS, priloge)
    assert res3.tier == "pomembni"
