"""GStack — arhitekturni manifest za Rob AI Studio.

Ustvari strukturirano specifikacijo modula (manifest) iz direktive.
Neodvisna, lahka implementacija; polnopravna živi v
``core.gstack_bridge.GSTACKArchitectBridge``.

Javni vmesniki:
- ``generate_manifest`` — vrne dict s projektom in seznamom datotek.
- ``ArchitectureBlueprint`` — majhna nemo strranska dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

__version__ = "0.1.0"
__all__ = ["generate_manifest", "ArchitectureBlueprint"]

# Razvojna ogrodja, ki jih sistem uporablja za svoje module.
DEFAULT_SCHEMA_FILES = [
    "schemas.py",
    "core.py",
    "main.py",
    "test_core.py",
]


@dataclass
class ArchitectureBlueprint:
    """Opisna specifikacija arhitekture modula."""

    project_name: str
    target_dir: str
    files: List[str] = field(default_factory=list)

    def as_manifest(self) -> Dict[str, object]:
        return {
            "project_name": self.project_name,
            "target_dir": self.target_dir,
            "files": self.files,
        }


def generate_manifest(project: str, directive: str, blacklists: List[str] | None = None) -> Dict[str, object]:
    """Iz direktive sestavi manifest.

    Args:
        project: ime modula (npr. ``demo_service``).
        directive: opis funkcije / zahtevka.
        blacklists: seznam znanih napak (neobvezno, za kontekst).

    Returns:
        Dict z ``project_name``, ``target_dir`` in ``files``.
    """
    target = f"actions/{project}"
    blueprint = ArchitectureBlueprint(
        project_name=project,
        target_dir=target,
        files=[f"{target}/{fname}" for fname in DEFAULT_SCHEMA_FILES],
    )
    manifest = blueprint.as_manifest()
    manifest["directive"] = directive
    manifest["known_blacklists"] = list(blacklists or [])
    return manifest
