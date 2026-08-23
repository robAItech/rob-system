"""tokenizer.py — razčlenjevanje niza v seznam besed.

Ločila in presledki se odstranijo, besede se normalizirajo na male črke.
"""

import re
from typing import List

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")


def tokenize(text: str) -> List[str]:
    """Razčleni niz v seznam besed (male črke, brez ločil).

    Args:
        text: vhodni niz (mora biti str).

    Returns:
        Seznam besed; prazen seznam za prazen vhod.

    Raises:
        TypeError: če `text` ni niz.
    """
    if not isinstance(text, str):
        raise TypeError(f"tokenize() pričakuje str, dobil {type(text).__name__}")
    return [token.lower() for token in _WORD_RE.findall(text)]