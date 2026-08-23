"""config_loader.py — čisto, samozadostno razčlenjevanje .env in INI vsebin.

Konsolidiran modul (združuje nekdanje env_config, ini_config in config_manager)
z vso razčlenjevalno logiko INLINE — brez odvisnosti od drugih actions modulov.

Javni API (po direktivi):
  * ``parse_env(text) -> dict[str, str]``
  * ``load_env(path) -> dict[str, str]``
  * ``parse_ini(text) -> dict[str, dict[str, str]]``
  * ``read_ini(path) -> dict[str, dict[str, str]]``
  * ``class ConfigManager(*sources)``
  * ``merge_env(*sources) -> dict[str, str]``
"""

from __future__ import annotations

import os
from collections.abc import ItemsView, Mapping
from pathlib import Path
from typing import Any, Dict, Optional, Union

__all__ = [
    "parse_env",
    "load_env",
    "parse_ini",
    "read_ini",
    "ConfigManager",
    "merge_env",
]

PathLike = Union[str, os.PathLike]


def parse_env(text: str) -> Dict[str, str]:
    """Razčleni .env vsebino (niz) v ``dict[str, str]``.

    Pravila:
      * prazne vrstice in vrstice s komentarjem (``#`` na začetku) se preskočijo;
      * opcijski prefiks ``export `` se odstrani;
      * ključ in vrednost se ločita na PRVEM ``=``;
      * ključ in vrednost se obrežeta (vodilni/sklepni presledki odpadejo);
      * navedena vrednost (``'...'`` ali ``"..."``) se od-navedi DOBESEDNO —
        tudi ``#`` in presledki v njej ostanejo;
      * pri nenavedeni vrednosti se inline komentar ``' # ...'`` odstrani,
        ``#`` brez presledka pred njim pa ostane;
      * zadnja pojavitev ključa zmaga;
      * ``os.environ`` se NE mutira.
    """
    if not isinstance(text, str):
        raise TypeError(f"parse_env: pričakovan str, dobil {type(text).__name__}")

    result: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
            if not line or line.startswith("#"):
                continue
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            # navedeno — od-navedi dobesedno, # in presledki ostanejo
            value = value[1:-1]
        else:
            # nenavedeno — odstrani inline komentar ' # ...'
            idx = value.find(" #")
            if idx != -1:
                value = value[:idx].strip()

        result[key] = value

    return result


def load_env(path: PathLike) -> Dict[str, str]:
    """Prebere UTF-8 .env datoteko in vrne ``parse_env`` njenih vsebin.

    Manjkajoča datoteka dvigne ``FileNotFoundError``.
    """
    return parse_env(Path(path).read_text(encoding="utf-8"))


def parse_ini(text: str) -> Dict[str, Dict[str, str]]:
    """Razčleni INI vsebino (niz) v ``dict[str, dict[str, str]]``.

    Pravila:
      * komentarji (``#`` in ``;``) in prazne vrstice se preskočijo;
      * ``[sekcija]`` odpre novo sekcijo (nadaljnji ključi gredo vanjo);
      * vrstice pred prvo sekcijo gredo v sekcijo ``''``;
      * ločilo je ``=``, ``:`` ali presledek;
      * ponovljene sekcije se združijo, ponovljeni ključi se prepišejo;
      * vhod, ki ni ``str``, dvigne ``TypeError``.
    """
    if not isinstance(text, str):
        raise TypeError(f"parse_ini: pričakovan str, dobil {type(text).__name__}")

    result: Dict[str, Dict[str, str]] = {}
    current: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section not in result:
                result[section] = {}
            current = section
            continue

        eq = line.find("=")
        colon = line.find(":")
        if eq != -1 and (colon == -1 or eq < colon):
            key, value = line[:eq], line[eq + 1:]
        elif colon != -1:
            key, value = line[:colon], line[colon + 1:]
        else:
            parts = line.split(None, 1)
            if len(parts) == 2:
                key, value = parts[0], parts[1]
            else:
                key, value = line, ""

        target = result[current] if current is not None else result.setdefault("", {})
        target[key.strip()] = value.strip()

    return result


def read_ini(path: PathLike) -> Dict[str, Dict[str, str]]:
    """Prebere UTF-8 INI datoteko in vrne ``parse_ini`` njenih vsebin.

    Manjkajoča datoteka dvigne ``FileNotFoundError``.
    """
    return parse_ini(Path(path).read_text(encoding="utf-8"))


class ConfigManager:
    """Združi poljubno število virov — 'later wins'.

    Vsak vir je lahko:
      * ``Mapping`` (npr. slovar),
      * surov niz z .env vsebino,
      * pot do obstoječe .env datoteke (``str`` ali ``os.PathLike``).
    """

    def __init__(self, *sources: Any) -> None:
        self._data: Dict[str, str] = {}
        for source in sources:
            self._absorb(source)

    def _absorb(self, source: Any) -> None:
        if isinstance(source, Mapping):
            data = dict(source)
        elif isinstance(source, (str, os.PathLike)):
            path = Path(source)
            if path.is_file():
                data = parse_env(path.read_text(encoding="utf-8"))
            else:
                data = parse_env(str(source))
        else:
            raise TypeError(
                f"ConfigManager: nepodprt tip vira: {type(source).__name__}"
            )
        self._data.update(data)

    def get(self, key: str, default: Any = None) -> Any:
        """Vrni vrednost ključa ali ``default``, če ključ ne obstaja."""
        return self._data.get(key, default)

    def all(self) -> Dict[str, str]:
        """Vrni kopijo celotnega združenega slovarja."""
        return dict(self._data)

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def items(self) -> ItemsView[str, str]:
        return self._data.items()

    def __repr__(self) -> str:
        return f"ConfigManager({self._data!r})"


def merge_env(*sources: Any) -> Dict[str, str]:
    """Združi vire prek ``ConfigManager`` in vrni končni slovar."""
    return ConfigManager(*sources).all()