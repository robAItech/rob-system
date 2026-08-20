"""
Skupni helper za prepoznavanje validnih action modulov.

Diagnostični skripti (dashboard, self-check, inspector) morajo enotno izločati
artefaktne / meta-mape (`.pytest_cache`, `__pycache__`, `.git`, ...). Brez tega
bi se skriti artefakti lažno šteli med "module" (npr. `./rob review` poroča 19
modulov namesto 18, ker šteje `.pytest_cache`).
"""

from pathlib import Path


def is_action_module(path: Path) -> bool:
    """
    Ali je direktorij veljaven action modul (ne skrit artefakt / meta-mapa).
    """
    return path.is_dir() and not path.name.startswith(".") and not path.name.startswith("__")


def list_action_modules(actions_dir: Path) -> list[Path]:
    """
    Vrni vse veljavne action module (urejeno). Prazen seznam, če map ni.
    """
    if not actions_dir.exists():
        return []
    return sorted(p for p in actions_dir.iterdir() if is_action_module(p))


def has_tests(module_dir: Path) -> bool:
    """
    Ali ima modul vsaj eno ``test_*.py`` datoteko (poljubno ime, ne nujno
    ``test_<ime_modula>.py`` — npr. api_gateway ima test_gateway.py ipd.).
    """
    return module_dir.is_dir() and any(module_dir.glob("test_*.py"))
