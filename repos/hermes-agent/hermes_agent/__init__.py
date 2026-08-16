"""Hermes-Agent — ogrodje (scaffold) modulov za Rob AI Studio.

Ustvari boilerplate datoteke (ogrodje) za nov modul v ``actions/``.
Neodvisen lahkot SDK; polnopravna implementacija živi v
``core.hermes_bridge.HermesBuilderBridge``.

Javni vmesniki:
- ``scaffold(project, target_dir)`` — zapiše osnovne stube.
- ``REQUIRED_FILES`` — spisek pričakovanih datotek modula.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

__version__ = "0.1.0"
__all__ = ["scaffold", "REQUIRED_FILES"]

# Standardne datoteke, ki jih vsak Rob AI modul vsebuje.
REQUIRED_FILES: List[str] = [
    "schemas.py",
    "core.py",
    "main.py",
    "test_core.py",
]


def scaffold(project: str, target_dir: str) -> List[str]:
    """Ustvari (če manjkajo) stubske datoteke modula.

    Args:
        project: ime modula.
        target_dir: pot na disku (npr. ``actions/{project}``).

    Returns:
        Seznam ustvarjenih / obstoječih datotek.
    """
    base = Path(target_dir)
    base.mkdir(parents=True, exist_ok=True)
    (base / "__init__.py").touch(exist_ok=True)

    made: List[str] = []
    for filename in REQUIRED_FILES:
        derived = filename.replace("core", project)
        fpath = base / derived
        if not fpath.exists() or fpath.stat().st_size == 0:
            fpath.write_text(f"# {project}: {filename.split('.')[0]} stub\n", encoding="utf-8")
        made.append(str(fpath))
    return made
