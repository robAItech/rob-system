"""test_text_proc.py — pytest testi za modul actions.text_proc.

Pokrivajo vse tri javne funkcije (tokenize, normalize, word_freq),
robne pogoje (prazen niz, presledki, ločila, velike črke, števke) ter
re-export javnega API-ja na nivoju paketa.
"""

import pytest

from actions.text_proc import normalize, tokenize, word_freq
from actions.text_proc import normalizer, stats, tokenizer


# ---------- tokenizer ----------

def test_tokenize_simple():
    assert tokenize("hello world") == ["hello", "world"]


def test_tokenize_lowercases():
    assert tokenize("Hello WORLD") == ["hello", "world"]


def test_tokenize_strips_punctuation():
    assert tokenize("Hello, World!") == ["hello", "world"]


def test_tokenize_empty():
    assert tokenize("") == []


def test_tokenize_whitespace_only():
    assert tokenize("   \t\n  ") == []


def test_tokenize_repeated_whitespace():
    assert tokenize("a  b   c") == ["a", "b", "c"]


def test_tokenize_digits():
    assert tokenize("item 123") == ["item", "123"]


def test_tokenize_non_string_raises():
    with pytest.raises(TypeError):
        tokenize(None)
    with pytest.raises(TypeError):
        tokenize(123)


# ---------- normalizer ----------

def test_normalize_lowercases_and_strips():
    assert normalize("  Hello   WORLD  ") == "hello world"


def test_normalize_collapses_whitespace():
    assert normalize("a\tb\nc") == "a b c"


def test_normalize_preserves_punctuation():
    assert normalize("Hello, World!") == "hello, world!"


def test_normalize_empty():
    assert normalize("") == ""


def test_normalize_whitespace_only():
    assert normalize("    ") == ""


def test_normalize_non_string_raises():
    with pytest.raises(TypeError):
        normalize(None)


# ---------- stats ----------

def test_word_freq_simple():
    assert word_freq("the cat and the dog") == {
        "the": 2,
        "cat": 1,
        "and": 1,
        "dog": 1,
    }


def test_word_freq_empty():
    assert word_freq("") == {}


def test_word_freq_case_insensitive():
    assert word_freq("a A a") == {"a": 3}


def test_word_freq_punctuation():
    assert word_freq("one, two. one!") == {"one": 2, "two": 1}


def test_word_freq_non_string_raises():
    with pytest.raises(TypeError):
        word_freq(None)


# ---------- javni API ----------

def test_public_api_reexports():
    assert callable(tokenize)
    assert callable(normalize)
    assert callable(word_freq)


def test_submodule_exports_are_same_objects():
    assert tokenizer.tokenize is tokenize
    assert normalizer.normalize is normalize
    assert stats.word_freq is word_freq
