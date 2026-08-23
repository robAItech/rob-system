"""stats.py — statistične funkcije nad besedilom (pogostost besed)."""

from typing import Dict

from actions.text_proc.tokenizer import tokenize


def word_freq(text: str) -> Dict[str, int]:
    """Vrni slovar pogostosti besed v nizu (male črke, brez ločil).

    Args:
        text: vhodni niz (mora biti str).

    Returns:
        Slovar {beseda: število pojavitev}; prazen slovar za prazen vhod.

    Raises:
        TypeError: če `text` ni niz.
    """
    if not isinstance(text, str):
        raise TypeError(f"word_freq() pričakuje str, dobil {type(text).__name__}")
    freq: Dict[str, int] = {}
    for token in tokenize(text):
        freq[token] = freq.get(token, 0) + 1
    return freq