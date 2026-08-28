"""Moving average: mean of each window of `okno` consecutive values."""

from typing import List, Sequence, Union


def moving_average(
    seznam: Sequence[Union[int, float]], okno: int
) -> List[float]:
    """Return the rolling mean of `seznam` over a window of `okno`.

    Raises:
        ValueError: if the sequence is empty, the window is not positive,
            or the window is larger than the sequence.
    """
    if okno <= 0:
        raise ValueError("okno must be > 0")
    if not seznam:
        raise ValueError("seznam must not be empty")
    if okno > len(seznam):
        raise ValueError("okno cannot be larger than seznam")

    return [
        sum(seznam[i : i + okno]) / okno
        for i in range(len(seznam) - okno + 1)
    ]