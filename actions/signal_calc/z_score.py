"""Z-score: how many standard deviations `x` is from the mean."""

import statistics
from typing import Sequence, Union


def z_score(
    vrednosti: Sequence[Union[int, float]], x: Union[int, float]
) -> float:
    """Return (x - mean) / population-std of `vrednosti` (0 for flat data).

    Raises:
        ValueError: if `vrednosti` is empty.
    """
    if not vrednosti:
        raise ValueError("vrednosti must not be empty")

    mean = statistics.fmean(vrednosti)
    variance = statistics.pvariance(vrednosti)
    if variance == 0:
        return 0.0
    return (x - mean) / (variance**0.5)