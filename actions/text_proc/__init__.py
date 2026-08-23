"""text_proc — čist javni API modula za obdelavo besedila.

Uporaba:
    from actions.text_proc import normalize, tokenize, word_freq
"""

from actions.text_proc.normalizer import normalize
from actions.text_proc.stats import word_freq
from actions.text_proc.tokenizer import tokenize

__all__ = ["normalize", "tokenize", "word_freq"]
__version__ = "1.0.0"