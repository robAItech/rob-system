"""
Skupni helper za prepoznavanje validnih action modulov.

Diagnostični skripti (dashboard, self-check, inspector) morajo enotno izločati
artefaktne / meta-mape (`.pytest_cache`, `__pycache__`, `.git`, ...). Brez tega
bi se skriti artefakti lažno šteli med "module" (npr. `./rob review` poroča 19
modulov namesto 18, ker šteje `.pytest_cache`).

Produkcijske izjeme (arhitekturna konsolidacija):
- ``fix_*`` — eval bugfix kloni (SWE-bench stil) se ustvarjajo ob eval teku in
  so NAMERNO bugirani; nikoli niso produkcijski moduli (isti razlog kot
  actions/conftest.py, ki jih izključi iz pytest collection).
- ``testmod_e`` — testni modul iz dev/test okolja; ne spada v produkcijski
  telemetry / runtime / deploy seznam.
"""

from pathlib import Path

#: Mape, ki jih NE štejemo kot produkcijske Action module.
NON_PRODUCTION_NAMES = frozenset({"testmod_e"})


def _is_production_action(path: Path) -> bool:
    """Ali je direktorij veljaven PRODUKCIJSKI action modul."""
    if not path.is_dir():
        return False
    if path.name.startswith(".") or path.name.startswith("__"):
        return False
    if path.name.startswith("fix_"):
        return False
    if path.name in NON_PRODUCTION_NAMES:
        return False
    return True


def is_action_module(path: Path) -> bool:
    """
    Ali je direktorij veljaven action modul (ne skrit artefakt / meta-mapa).
    """
    return _is_production_action(path)


def list_action_modules(actions_dir: Path) -> list[Path]:
    """
    Vrni vse veljavne PRODUKCIJSKE action module (urejeno). Prazen seznam,
    če map ni. Izključuje eval bugfix klone (``fix_*``), dev/test module
    (``testmod_e``), skrite in Python meta-mape.
    """
    if not actions_dir.exists():
        return []
    return sorted(p for p in actions_dir.iterdir() if _is_production_action(p))


def has_tests(module_dir: Path) -> bool:
    """
    Ali ima modul vsaj eno ``test_*.py`` datoteko (poljubno ime, ne nujno
    ``test_<ime_modula>.py`` — npr. api_gateway ima test_gateway.py ipd.).
    """
    return module_dir.is_dir() and any(module_dir.glob("test_*.py"))
