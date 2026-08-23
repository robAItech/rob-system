"""text_proc.py — jedro domenske logike.

Modul združuje podmodule tokenizer, normalizer in stats ter ponuja
priročne kombinirane funkcije. Javni API je re-exportiran na nivoju
paketa (glej __init__.py).
"""

from typing import Dict, List

from actions.text_proc.normalizer import normalize
from actions.text_proc.stats import word_freq
from actions.text_proc.tokenizer import tokenize

__all__ = ["normalize", "tokenize", "word_freq"]


def process(text: str) -> Dict[str, object]:
    """Pripravi vhodni niz in vrne slovar z izračunanimi metrikami."""
    normalized = normalize(text)
    tokens = tokenize(normalized)
    return {
        "normalized": normalized,
        "tokens": tokens,
        "word_count": len(tokens),
        "word_freq": word_freq(normalized),
    }