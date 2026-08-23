"""test_string_ops.py — port originalnih testov (slugify + truncate_text + text_proc).

Test je Test-Locked: daemon ga ne sme spreminjati. Natanko kodira semantiko
konsolidiranega modula string_ops.
"""
from __future__ import annotations

import pytest

from actions.string_ops import (normalize, slug, tokenize, truncate,
                                truncate_start, word_freq)


# ── slug ────────────────────────────────────────────────────────────────── #
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("HELLO", "hello"),
        ("Hello World", "hello-world"),
        ("Hello   World", "hello-world"),
        ("  Multiple   Spaces  ", "multiple-spaces"),
        ("a b c", "a-b-c"),
        ("Hello, World!", "hello-world"),
        ("Hello.World", "hello-world"),
        ("hello_world", "hello-world"),
        ("Version 2.0", "version-2-0"),
        ("a--b", "a-b"),
        ("a - b", "a-b"),
        ("-leading", "leading"),
        ("trailing-", "trailing"),
        ("---", ""),
        ("", ""),
        ("   ", ""),
        ("already-slugged", "already-slugged"),
        ("Café", "cafe"),
        ("Äpfel", "apfel"),
    ],
)
def test_slug_basic(text, expected):
    assert slug(text) == expected


def test_slug_rejects_non_string():
    with pytest.raises(TypeError):
        slug(None)
    with pytest.raises(TypeError):
        slug(123)


# ── truncate ────────────────────────────────────────────────────────────── #
def test_truncate_kratek_se_vrne_nespremenjen():
    assert truncate("Hello") == "Hello"
    assert truncate("") == ""
    assert truncate("abcd", 4) == "abcd"


def test_truncate_dolg_niz_se_skrajsa():
    niz = "a" * 100
    rezultat = truncate(niz, 80)
    assert len(rezultat) == 80
    assert rezultat == "a" * 77 + "..."


def test_truncate_ne_reze_sredi_besede():
    assert truncate("The quick brown fox", 15) == "The quick..."


def test_truncate_single_long_word_na_meji():
    assert truncate("Supercalifragilistic", 10) == "Superca..."


def test_truncate_custom_suffix():
    assert truncate("Hello world", 8, suffix="…") == "Hello…"


def test_truncate_prazen_suffix():
    assert truncate("Hello world", 8, suffix="") == "Hello"


def test_truncate_max_len_manjsi_od_suffixa():
    assert truncate("Hello", 3) == "Hel"


def test_truncate_max_len_nic():
    assert truncate("Hello", 0) == ""


def test_truncate_suffix_le_ob_skrajsanju():
    assert "..." not in truncate("Hello")
    assert truncate("Hello world", 8).endswith("...")


def test_truncate_rezultat_nikoli_ne_presega_max_len():
    for max_len in (0, 1, 5, 10, 79, 80, 81, 120):
        rezultat = truncate("x " * 100, max_len)
        assert len(rezultat) <= max_len


def test_truncate_unicode():
    assert truncate("čšž čšž čšž", 7) == "čšž..."


# ── truncate_start ──────────────────────────────────────────────────────── #
def test_truncate_start_kratek_se_vrne_nespremenjen():
    assert truncate_start("Hello") == "Hello"
    assert truncate_start("") == ""
    assert truncate_start("abcd", 4) == "abcd"


def test_truncate_start_dolg_niz():
    niz = "a" * 100
    rezultat = truncate_start(niz, 80)
    assert len(rezultat) == 80
    assert rezultat == "..." + "a" * 77


def test_truncate_start_obdrzi_konec_niza():
    assert truncate_start("The quick brown fox", 15) == "...brown fox"


def test_truncate_start_ne_reze_sredi_besede():
    assert truncate_start("The quick brown fox", 12) == "...brown fox"


def test_truncate_start_single_long_word():
    assert truncate_start("Supercalifragilistic", 10) == "...gilistic"


def test_truncate_start_custom_prefix():
    assert truncate_start("Hello world", 8, prefix="…") == "…world"


def test_truncate_start_prazen_prefix():
    assert truncate_start("Hello world", 8, prefix="") == "world"


def test_truncate_start_max_len_manjsi_od_prefixa():
    assert truncate_start("Hello", 3) == "llo"


def test_truncate_start_max_len_nic():
    assert truncate_start("Hello", 0) == ""


def test_truncate_start_prefix_le_ob_skrajsanju():
    assert "..." not in truncate_start("Hello")
    assert truncate_start("Hello world", 8).startswith("...")


def test_truncate_start_rezultat_nikoli_ne_presega_max_len():
    for max_len in (0, 1, 5, 10, 79, 80, 81, 120):
        rezultat = truncate_start("x " * 100, max_len)
        assert len(rezultat) <= max_len


# ── tokenize / normalize / word_freq ────────────────────────────────────── #
def test_tokenize_simple():
    assert tokenize("hello world") == ["hello", "world"]
    assert tokenize("Hello WORLD") == ["hello", "world"]
    assert tokenize("Hello, World!") == ["hello", "world"]
    assert tokenize("") == []
    assert tokenize("   \t\n  ") == []
    assert tokenize("a  b   c") == ["a", "b", "c"]
    assert tokenize("item 123") == ["item", "123"]


def test_tokenize_non_string_raises():
    with pytest.raises(TypeError):
        tokenize(None)


def test_normalize():
    assert normalize("  Hello   WORLD  ") == "hello world"
    assert normalize("a\tb\nc") == "a b c"
    assert normalize("Hello, World!") == "hello, world!"
    assert normalize("") == ""
    assert normalize("    ") == ""


def test_normalize_non_string_raises():
    with pytest.raises(TypeError):
        normalize(123)


def test_word_freq():
    assert word_freq("the cat and the dog") == {"the": 2, "cat": 1, "and": 1, "dog": 1}
    assert word_freq("") == {}
    assert word_freq("Hello hello HELLO") == {"hello": 3}


def test_word_freq_non_string_raises():
    with pytest.raises(TypeError):
        word_freq(None)
