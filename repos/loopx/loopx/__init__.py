"""LoopX — verifikacijska in samoozdravitvena zanka za Rob AI Studio.

Ta paket ponuja zgoščen "SDK" dostop do zanke: meri zaporedja korakov
(check/attempt-cikluse) in po potrebi ponavlja, idelno z morebitnim
poročilom o vsakem poskusu. Polnopravna izvedba (z Pytest + LLM healingom)
živi v ``core.loopx_bridge.LoopXEngineBridge``.

Javni vmesniki:
- ``Loop`` — preprost dnevnik poskusov (attempt) s statusno oznako.
- ``heal_threshold`` — pomožna konstanta za privzeti število poskusov.
"""

from __future__ import annotations

from typing import Dict, List, Optional

__version__ = "0.1.0"
__all__ = ["Loop", "heal_threshold"]

# Privzeto število poskusov v samoozdravitveni zanki (usklajeno z LoopX).
heal_threshold = 5


class Loop:
    """Sledi poskusom zanke in vrača njihovo zgodovino.

    Primer uporabe v samostojni integraciji (brez produkcijskega mosta)::

        lp = Loop()
        lp.try_step("pytest", ok=False, note="ImportError")
        lp.try_step("pytest", ok=True, note="healed")
        lp.status  # -> "OK"
    """

    def __init__(self, max_attempts: int = heal_threshold) -> None:
        self.max_attempts = max_attempts
        self.attempts: List[Dict[str, object]] = []

    def try_step(self, name: str = "check", ok: bool = False, note: str = "") -> None:
        """Zabeleži en poskus (check)."""
        self.attempts.append({"name": name, "ok": ok, "note": note})

    @property
    def status(self) -> str:
        """'OK' če vsaj en poskus uspel, 'FAILED' če ni, 'PENDING' sicer."""
        if not self.attempts:
            return "PENDING"
        return "OK" if any(a.get("ok") for a in self.attempts) else "FAILED"

    def last_note(self) -> Optional[str]:
        """Poročilo / traceback zadnjega poskusa, če obstaja."""
        if not self.attempts:
            return None
        note = self.attempts[-1].get("note") or ""
        return str(note) if note else None
