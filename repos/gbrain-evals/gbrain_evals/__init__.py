"""GBrain-Evals — vrednotenje spomina in napovednika za Rob AI Studio.

Neodvisen, lahkot "SDK" za ocenjevanje uspešnosti spominskih vpisov /
napovedi. Uvozi kot ``gbrain_evals`` (Python normalizira dash v underscore).

Javni vmesniki:
- ``score`` — preprosta metrična ocena (accuracy) iz n-tuple odgovorov.
- ``EvalResult`` — struktura za en rezultat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Tuple

__version__ = "0.1.0"
__all__ = ["score", "EvalResult"]


@dataclass
class EvalResult:
    """Eden rezultat vrednotenja."""

    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return (self.correct / self.total) if self.total else 0.0


def score(answers: Iterable[Tuple[bool, bool]]) -> EvalResult:
    """Izračuna accuracy med napovedmi in resničnimi vrednostmi.

    Args:
        answers: iterable ``(napoved, res)`` parov.

    Returns:
        ``EvalResult`` s številkami.
    """
    pairs = list(answers)
    total = len(pairs)
    correct = sum(1 for pred, truth in pairs if pred == truth)
    return EvalResult(total=total, correct=correct)
