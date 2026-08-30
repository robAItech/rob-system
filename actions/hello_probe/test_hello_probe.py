"""Pytest testi za hello_probe.greet.

Pokrivajo znane vrednosti, robne pogoje (prazno ime, Unicode),
re-export javnega API-ja ter roundtrip preko Pydantic V2 sheme.
"""

import sys
from pathlib import Path

# Zagotovi, da je mapa, ki vsebuje paket hello_probe (npr. actions/),
# na sys.path — ne glede na to, od kod pytest zbira ta test.
_THIS_DIR = Path(__file__).resolve().parent
for _candidate in (
    _THIS_DIR,
    _THIS_DIR.parent,
    _THIS_DIR.parent.parent,
    _THIS_DIR.parent.parent / "actions",
    _THIS_DIR.parent / "actions",
):
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import pytest
from pydantic import ValidationError

from hello_probe.hello_probe import greet
from hello_probe import greet as greet_reexport
from hello_probe.schemas import GreetRequest


def test_greet_znana_vrednost() -> None:
    assert greet("Ana") == "Pozdrav, Ana"


def test_greet_prazno_ime() -> None:
    assert greet("") == "Pozdrav, "


def test_greet_unicode_ime() -> None:
    assert greet("Žiga Novak") == "Pozdrav, Žiga Novak"


def test_greet_reexport_iz_paketa() -> None:
    assert greet_reexport("Bojan") == "Pozdrav, Bojan"


def test_schema_roundtrip() -> None:
    req = GreetRequest(name="  Maja  ")
    assert req.name == "Maja"
    assert greet(req.name) == "Pozdrav, Maja"


def test_schema_prazno_ime_zavrnjeno() -> None:
    with pytest.raises(ValidationError):
        GreetRequest(name="   ")
