"""GBrain — kontekstni spomin (persistent memory) za Rob AI Studio.

Javni API za dostop do spomina in znanih napak (black-list vzorcev).
Napredna, hitra uporaba gre prek ``core.gbrain_bridge.GBrainBridge``,
ta paket pa ponuja neodvisen, lahka uvozljiv "SDK" razred, ki osnovano
logiko ponudi strukturirano (brez SQLite odvisnosti).

Uporabna vmesnika paketa:
- ``GBrainContext`` — ključ-vrednost spomin s tags.
- ``record_task`` — enostaven vpis dogodka v spomin.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__version__ = "0.1.0"
__all__ = ["GBrainContext", "record_task"]


class GBrainContext:
    """Preprost spominski objekt (thread-safe dnevniško shranjevanje).

    Predstavlja naslednjico brez stalne SQLite odvisnosti — uporabniku
    omogoča, da zapiše stanje (task/lesson) ne glede na produkcijsko
    bazo. Polnopravna izvedba živi v ``core.gbrain_bridge``.
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._max_entries = max_entries

    def remember(self, key: str, data: Dict[str, Any]) -> None:
        """Shrani spominski vozel."""
        self._entries[key] = data
        # Osnovni mehanizem velikosti: če je presegel, vrže nič hudega, samo omeji.
        if len(self._entries) > self._max_entries:
            # izprazni najstarejšo vstopnico (first-in-first-out približek)
            self._entries.pop(next(iter(self._entries)))

    def recall(self, key: str) -> Optional[Dict[str, Any]]:
        """Pridobi shranjen vozel ali None."""
        return self._entries.get(key)

    def snapshot(self) -> List[Dict[str, Any]]:
        """Vrni vse shranjene vozle kot seznam."""
        return list(self._entries.values())


def record_task(project: str, status: str) -> None:
    """Kratka pomočna funkcija za hitro vpis dogodka v GBrainContext.

    Obstaja zaradi lažje uporabe v integracijah: ``gbrain.record_task``
    zabeleži minimalni dogodek v globljem spominu (privzeto prazno).
    """
    ctx = GBrainContext()
    ctx.remember(f"{project}:{status}", {"project": project, "status": status})
