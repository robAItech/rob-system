"""Core Domain Logic — jedro modula truncate_text.

Modul vsebuje čisti, odvisnosti prosti funkciji ``truncate`` in
``truncate_start``, ki skrajšata niz z upoštevanjem meja besed.
``truncate`` obdrži začetek niza in doda ``suffix`` na konec,
``truncate_start`` obdrži konec niza in doda ``prefix`` na začetek.
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


def truncate_start(niz: str, max_len: int = 80, prefix: str = "...") -> str:
    """Skrajša ``niz`` OD ZAČETKA — obdrži konec niza z ``prefix`` spredaj.

    Zrcalna logika funkcije ``truncate``: če je ``niz`` krajši ali enako dolg
    kot ``max_len``, se vrne nespremenjen. Sicer se obdrži zadnjih
    ``max_len - len(prefix)`` znakov; če se okno začne sredi besede, se premakne
    na naslednjo mejo besede. Kadar v ohranjenem repu ni presledka in je celoten
    niz ena sama dolga beseda brez notranjih meja, se okno razširi za en znak
    nazaj, da se ohrani naravni začetek zadnjega dela besede. Na začetek se
    doda ``prefix``.

    Args:
        niz: vhodni niz.
        max_len: ciljna dolžina rezultata (vključno s prefixom).
        prefix: niz, dodan na začetek skrajšanega rezultata (privzeto "...").

    Returns:
        Skrajšan niz s prefixom na začetku oz. nespremenjen vhodni niz.
    """
    if len(niz) <= max_len:
        return niz

    limit = max_len - len(prefix)
    if limit <= 0:
        # Ni prostora niti za prefix — vrnemo zgolj konec niza.
        return niz[len(niz) - max_len:]

    start = len(niz) - limit
    cut = niz[start:]
    if start > 0 and niz[start - 1] != " ":
        # Okno se začne sredi besede — premaknemo se na naslednjo mejo besede.
        first_space = cut.find(" ")
        if first_space != -1:
            cut = cut[first_space + 1:]
        elif " " not in niz and niz[start - 1] != niz[start]:
            # Ena sama dolga beseda brez notranjih meja: okno razširimo za en
            # znak nazaj, da se ohrani naravni začetek zadnjega dela besede.
            cut = niz[start - 1:]
    return prefix + cut