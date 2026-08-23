"""Pytest Test Suite — truncate_start funkcija modula truncate_text."""

import sys
from pathlib import Path

# Robusten uvoz ne glede na to, ali je projektni koren ali actions/ na sys.path.
_ROOT = Path(__file__).resolve().parents[1]  # actions/
_WORK = Path(__file__).resolve().parents[2]  # projektni koren
for _p in (str(_WORK), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from actions.truncate_text import truncate_start
except ImportError:  # pragma: no cover — odvisno od postavitve sys.path
    from truncate_text import truncate_start


def test_kratek_niz_se_vrne_nespremenjen():
    assert truncate_start("Hello") == "Hello"


def test_prazen_niz_se_vrne_nespremenjen():
    assert truncate_start("") == ""


def test_niz_tocno_max_len_se_vrne_nespremenjen():
    niz = "a" * 80
    assert truncate_start(niz) == niz


def test_niz_z_max_len_manjsega_od_privzetega_se_vrne_nespremenjen():
    assert truncate_start("abcd", 4) == "abcd"


def test_dolg_niz_se_skrajsa_na_max_len():
    rezultat = truncate_start("a" * 100)
    assert len(rezultat) == 80
    assert rezultat == "..." + "a" * 77


def test_obdrzi_konec_niza():
    assert truncate_start("The quick brown fox", 15) == "...brown fox"


def test_ne_reze_sredi_besede():
    # Rezultat se začne na meji besede, ne sredi besede.
    assert truncate_start("The quick brown fox", 12) == "...brown fox"


def test_single_long_word_se_odreze_na_meji():
    assert truncate_start("Supercalifragilistic", 10) == "...gilistic"


def test_custom_prefix():
    assert truncate_start("Hello world", 8, prefix="…") == "…world"


def test_prazen_prefix():
    assert truncate_start("Hello world", 8, prefix="") == "world"


def test_max_len_manjsi_od_prefixa():
    assert truncate_start("Hello", 3) == "llo"


def test_max_len_nic():
    assert truncate_start("Hello", 0) == ""


def test_prefix_se_doda_le_ob_skrajsanju():
    assert "..." not in truncate_start("Hello")
    assert truncate_start("Hello world", 8).startswith("...")


def test_rezultat_nikoli_ne_presega_max_len():
    niz = "The quick brown fox jumps over the lazy dog"
    for max_len in (1, 2, 3, 5, 10, 15, 79, 80, 81, 100):
        rezultat = truncate_start(niz, max_len)
        assert len(rezultat) <= max_len


def test_unicode_niz_se_skrajsa_po_znakih():
    assert truncate_start("čšž čšž čšž", 7) == "...čšž"


def test_privzeti_max_len_je_80():
    assert truncate_start("x" * 200) == "..." + "x" * 77
