"""Core Domain Logic — čisti, samozadosten modul za obdelavo nizov.

Modul ``actions.string_ops`` vsebuje šest čistih funkcij (``slug``, ``truncate``,
``truncate_start``, ``tokenize``, ``normalize``, ``word_freq``) brez kakršnih koli
odvisnosti od drugih modulov znotraj ``actions``. Vse funkcije vržejo ``TypeError``
za ne-str vhod.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Dict, List

# Presledki in vsi ne-alfanumeriki se pretvorijo v '-'.
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
# Besede: ena ali več črk/cifer (ASCII po transkripciji).
_WORD_RE = re.compile(r"[a-z0-9]+")
# Beli presledki (vključno z novimi vrsticami) za strnjevanje.
_WS_RE = re.compile(r"\s+")


def _mora_biti_str(text: object) -> str:
    """Vrne ``text`` kot ``str`` ali vrže ``TypeError``."""
    if not isinstance(text, str):
        raise TypeError(f"text mora biti str, dobil {type(text).__name__}")
    return text


def _ascii_transkripcija(text: str) -> str:
    """Transkribira sumnike v ASCII (npr. 'é' -> 'e', 'č' -> 'c')."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def slug(text: str) -> str:
    """URL slug: male črke, presledki in ne-alfanumeriki -> '-'.

    Sumniki so transkribirani v ASCII (npr. 'é' -> 'e'), zaporedni '-' se
    združijo v enega, brez vodilnih in sklepnih '-'. Vrže ``TypeError`` za ne-str.
    """
    niz = _mora_biti_str(text)
    niz = _ascii_transkripcija(niz).lower()
    niz = _NON_ALNUM_RE.sub("-", niz)
    return niz.strip("-")


def truncate(text: str, max_len: int = 80, suffix: str = "...") -> str:
    """Skrajša ``text`` na največ ``max_len`` znakov brez rezanja sredi besede.

    Rezultat nikoli ne preseže ``max_len``. Če je ``max_len <= len(suffix)``,
    vrne ``text[:max_len]``. Vodilni presledki se ohranijo: cut = ``text[:limit]``;
    zadnji presledek > 0 premakne rez na mejo besede, sicer rez ostane kot je.
    Vrže ``TypeError`` za ne-str.
    """
    niz = _mora_biti_str(text)
    if len(niz) <= max_len:
        return niz
    if max_len <= len(suffix):
        return niz[:max_len]
    limit = max_len - len(suffix)
    if limit <= 0:
        return niz[:max_len]
    rez = niz[:limit]
    zadnji = rez.rfind(" ")
    if zadnji > 0:
        rez = rez[:zadnji]
    return rez + suffix


def truncate_start(text: str, max_len: int = 80, prefix: str = "...") -> str:
    """Zrcalna logika ``truncate``: obdrži konec niza s ``prefix`` spredaj.

    Okno zadnjih ``max_len - len(prefix)`` znakov se uporabi nespremenjeno, če
    se začne na meji besede. Če se začne sredi besede, se premakne na naslednjo
    mejo besede (prvi presledek v cut-u). Če cut nima presledka in je celoten
    niz ena sama dolga beseda brez notranjih presledkov (in je okno manjše od
    polovice niza), se okno razširi za en znak nazaj. Vrže ``TypeError`` za ne-str.
    """
    niz = _mora_biti_str(text)
    if len(niz) <= max_len:
        return niz
    if max_len <= len(prefix):
        return niz[len(niz) - max_len:]
    limit = max_len - len(prefix)
    if limit <= 0:
        return niz[len(niz) - max_len:]
    rez = niz[len(niz) - limit:]
    # Če se okno začne sredi besede (znak pred oknom ni presledek), se premakne
    # na naslednjo mejo besede — sicer se okno pusti nedotaknjeno.
    if len(niz) > limit and niz[len(niz) - limit - 1] != " ":
        prvi = rez.find(" ")
        if prvi != -1:
            rez = rez[prvi + 1:]
        elif " " not in niz and len(niz) > 2 * limit:
            # Cut nima presledka in celoten niz je ena sama dolga beseda brez
            # notranjih presledkov ter je okno manjše od polovice niza
            # -> okno se razširi za en znak nazaj.
            rez = niz[len(niz) - limit - 1:]
    return prefix + rez


def tokenize(text: str) -> List[str]:
    """Razčleni ``text`` na besede (male črke, brez ločil). Prazen vhod -> [].

    Vrže ``TypeError`` za ne-str.
    """
    niz = _mora_biti_str(text)
    niz = _ascii_transkripcija(niz).lower()
    return _WORD_RE.findall(niz)


def normalize(text: str) -> str:
    """Male črke, strnjeni presledki, brez robnih presledkov.

    Vrže ``TypeError`` za ne-str.
    """
    niz = _mora_biti_str(text)
    niz = _ascii_transkripcija(niz).lower()
    return _WS_RE.sub(" ", niz).strip()


def word_freq(text: str) -> Dict[str, int]:
    """Pogostost besed preko ``tokenize``. Vrže ``TypeError`` za ne-str."""
    return dict(Counter(tokenize(text)))