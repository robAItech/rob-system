"""Core Domain Logic — jedro modula truncate_text.

Modul vsebuje čisto, odvisnosti prosto funkcijo ``truncate``, ki skrajša
niz na največ ``max_len`` znakov brez rezanja sredi besede.
"""

from __future__ import annotations


def truncate(niz: str, max_len: int = 80, suffix: str = "...") -> str:
    """Skrajša ``niz`` na največ ``max_len`` znakov brez rezanja sredi besede.

    Če je ``niz`` krajši ali enako dolg kot ``max_len``, se vrne nespremenjen.
    Sicer se niz odreže na ``max_len - len(suffix)`` znakov in rez premakne na
    zadnji presledek pred mejo (če obstaja), na konec pa se doda ``suffix``.
    Rezultat nikoli ne preseže ``max_len`` znakov.

    Args:
        niz: vhodni niz.
        max_len: največja dovoljena dolžina rezultata (vključno s suffixom).
        suffix: niz, dodan na konec skrajšanega rezultata (privzeto "...").

    Returns:
        Skrajšan niz z dodanim suffixom oz. nespremenjen vhodni niz.
    """
    if len(niz) <= max_len:
        return niz

    limit = max_len - len(suffix)
    if limit <= 0:
        # Ni prostora niti za suffix — vrnemo zgolj začetek niza.
        return niz[:max_len]

    cut = niz[:limit]
    last_space = cut.rfind(" ")
    if last_space > 0:
        cut = cut[:last_space]
    return cut + suffix