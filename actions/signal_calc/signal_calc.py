"""Core domain logic for the signal_calc module.

Pure, dependency-free helpers:
  - moving_average(seznam, okno): klizno povprecje seznama.
  - z_score(vrednosti, x): standardizacija vrednosti x znotraj populacije.
  - clamp(v, min, max): omejitev vrednosti na interval [min, max].
"""

import statistics


def moving_average(seznam, okno):
    """Vrni seznam kliznih povprecij dolzine ``okno`` nad ``seznam``.

    Rezultat ima ``len(seznam) - okno + 1`` elementov; vsak element je
    povprecje ``okno`` zaporednih vrednosti.

    Raises:
        ValueError: ce je ``okno`` <= 0, ce je ``seznam`` prazen ali ce je
            ``okno`` vecje od dolzine seznama.
    """
    if okno <= 0:
        raise ValueError("okno mora biti pozitivno stevilo")
    if not seznam:
        raise ValueError("seznam ne sme biti prazen")
    if okno > len(seznam):
        raise ValueError("okno ne sme biti vecje od dolzine seznama")
    return [
        sum(seznam[i:i + okno]) / okno
        for i in range(len(seznam) - okno + 1)
    ]


def z_score(vrednosti, x):
    """Vrni z-vrednost ``x`` znotraj ``vrednosti``.

    Uporablja populacijsko standardno deviacijo (``statistics.pstdev``).
    Ce je standardna deviacija 0 (konstantna ali enoelementna serija),
    vrne 0.0.

    Raises:
        ValueError: ce je ``vrednosti`` prazen seznam.
    """
    if not vrednosti:
        raise ValueError("vrednosti ne smejo biti prazne")
    povprecje = statistics.fmean(vrednosti)
    sdev = statistics.pstdev(vrednosti)
    if sdev == 0:
        return 0.0
    return (x - povprecje) / sdev


def clamp(v, min, max):
    """Omeji vrednost ``v`` na interval [min, max].

    - v < min  -> min
    - v > max  -> max
    - sicer    -> v
    """
    if v < min:
        return min
    if v > max:
        return max
    return v
