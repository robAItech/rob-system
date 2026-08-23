"""Pytest Test Suite — truncate_text modul."""

import sys
from pathlib import Path

# Robusten uvoz ne glede na to, ali je projektni koren ali actions/ na sys.path.
_ROOT = Path(__file__).resolve().parents[1]  # actions/
_WORK = Path(__file__).resolve().parents[2]  # projektni koren
for _p in (str(_WORK), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from actions.truncate_text import truncate
except ImportError:  # pragma: no cover — odvisno od postavitve sys.path
    from truncate_text import truncate


def test_kratek_niz_se_vrne_nespremenjen():
    assert truncate("Hello") == "Hello"


def test_prazen_niz_se_vrne_nespremenjen():
    assert truncate("") == ""


def test_niz_tocno_max_len_se_vrne_nespremenjen():
    niz = "a" * 80
    assert truncate(niz) == niz


def test_niz_z_max_len_manjsega_od_privzetega_se_vrne_nespremenjen():
    assert truncate("abcd", 4) == "abcd"


def test_dolg_niz_se_skrajsa_na_max_len():
    rezultat = truncate("a" * 100)
    assert len(rezultat) == 80
    assert rezultat == "a" * 77 + "..."


def test_ne_reze_sredi_besede():
    assert truncate("The quick brown fox", 15) == "The quick..."


def test_single_long_word_se_odreze_na_meji():
    assert truncate("Supercalifragilistic", 10) == "Superca..."


def test_custom_suffix():
    assert truncate("Hello world", 8, suffix="…") == "Hello…"


def test_prazen_suffix():
    assert truncate("Hello world", 8, suffix="") == "Hello"


def test_max_len_manjsi_od_suffixa():
    assert truncate("Hello", 3) == "Hel"


def test_max_len_nic():
    assert truncate("Hello", 0) == ""


def test_suffix_se_doda_le_ob_skrajsanju():
    assert "..." not in truncate("Hello")
    assert truncate("Hello world", 8).endswith("...")


def test_rezultat_nikoli_ne_presega_max_len():
    niz = "The quick brown fox jumps over the lazy dog"
    for max_len in (1, 2, 3, 5, 10, 15, 79, 80, 81, 100):
        rezultat = truncate(niz, max_len)
        assert len(rezultat) <= max_len


def test_unicode_niz_se_skrajsa_po_znakih():
    assert truncate("čšž čšž čšž", 7) == "čšž..."


def test_privzeti_max_len_je_80():
    assert truncate("x" * 200) == "x" * 77 + "..."
