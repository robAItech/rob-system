"""env_config — čisto razčlenjevanje .env vsebine v Python slovarje.

Javni API (po direktivi):
  * ``parse_env(text: str) -> dict[str, str]``  — razčleni .env vsebino (niz).
  * ``load_env(path: str | Path) -> dict[str, str]`` — prebere .env datoteko
    in vrne njen razčlenjen slovar.
"""

from pathlib import Path
from typing import Dict, Union

__all__ = ["parse_env", "load_env"]


def parse_env(text: str) -> Dict[str, str]:
    """Razčleni .env vsebino v ``dict[str, str]``.

    Pravila razčlenjevanja:
      * prazne vrstice in vrstice s komentarjem (``#`` na začetku) se preskočijo;
      * opcijski prefiks ``export `` se odstrani;
      * ključ in vrednost se ločita na prvem ``=``;
      * ključ/vrednost se obrežeta (brez vodilnih/sklepnih presledkov);
      * vrednost, obdana z enojnimi ali dvojnimi narekovaji, se od-navedi
        (vsebina se ohrani dobesedno, tudi ``#`` in presledki);
      * pri nenavedenih vrednostih se inline komentar (`` # ...``) odstrani;
      * zadnja pojavitev ključa zmaga (duplikati se prepišejo).
    """
    result: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if value and value[0] in ('"', "'"):
            quote = value[0]
            end = value.find(quote, 1)
            if end != -1:
                value = value[1:end]
            else:
                value = value[1:]
        else:
            hash_idx = value.find("#")
            if hash_idx > 0 and value[hash_idx - 1].isspace():
                value = value[:hash_idx].rstrip()
        result[key] = value
    return result


def load_env(path: Union[str, Path]) -> Dict[str, str]:
    """Prebere .env datoteko s poti ``path`` in vrne razčlenjen slovar.

    Če datoteka ne obstaja, se dvigne ``FileNotFoundError`` (naravno vedenje
    ``open``) — funkcija ne požira napak in ne spreminja procesnega okolja
    (``os.environ``).
    """
    with open(path, "r", encoding="utf-8") as handle:
        return parse_env(handle.read())