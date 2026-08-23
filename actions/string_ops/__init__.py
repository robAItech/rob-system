"""actions.string_ops — čist, samozadosten modul za obdelavo nizov.

Javni API na nivoju paketa (re-eksportiran tudi tukaj):

    from actions.string_ops import slug, truncate, truncate_start, tokenize,
                                   normalize, word_freq
"""

from .string_ops import (
    normalize,
    slug,
    tokenize,
    truncate,
    truncate_start,
    word_freq,
)

__all__ = [
    "slug",
    "truncate",
    "truncate_start",
    "tokenize",
    "normalize",
    "word_freq",
]
