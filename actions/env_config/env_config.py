"""env_config.py — razčlenjevanje .env datotek (parse_env + load_env).

Enoten, varen parser .env → dict: preskoči komentarje in prazne vrstice,
odstrani narekovaje okoli vrednosti in tolerira malformed vrstice (jih
preskoči, ne pade). Ista logika kot `core.dev_cli.parse_env` (preizkušena v
produkciji) — tukaj kot samostojen, testiran modul v actions/.
"""

from pathlib import Path
from typing import Dict


def parse_env(text: str) -> Dict[str, str]:
    """Razčleni .env tekst v dict.

    Pravila:
      - prazne vrstice in komentarji (``#``) se preskočijo,
      - vsaka vrstica ``ime=vrednost``; vrednost se strip-a in po potrebi
        odpravi dvojne ali navadne narekovaje,
      - malformed vrstice (brez ``=`` ali brez imena) se preskočijo (tolerantno),
      - deli se pri PRVEM ``=``, tako da vrednost lahko vsebuje ``=`` (npr. URL).

    Args:
        text: vsebina .env datoteke (str).

    Returns:
        dict {ime: vrednost}.
    """
    out: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        eq = line.find("=")
        if eq <= 0:
            continue
        name = line[:eq].strip()
        val = line[eq + 1:].strip().strip('"').strip("'")
        if name:
            out[name] = val
    return out


def load_env(path: Path | str) -> Dict[str, str]:
    """Prebere .env datoteko (UTF-8) in jo razčleni v dict.

    Args:
        path: pot do .env datoteke.

    Returns:
        dict {ime: vrednost}.

    Raises:
        FileNotFoundError: če datoteka ne obstaja.
        OSError: če branje ni uspelo.
    """
    return parse_env(Path(path).read_text(encoding="utf-8"))
