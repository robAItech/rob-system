"""secret_rotation — jedro domenske logike: avtomatizirana rotacija skrivnosti.

Kot predlaga arhitekturna revizija (3.3): self-service rotacija API ključev, DB
gesel in certifikatov brez downtime. Jedro:
  - double-buffer pattern: aktivna → pripravljena (staged) → pasivna (zero-downtime),
  - scheduler: ``due_secrets(now)`` vrne skrivnosti, ki jim poteče interval,
  - audit sled za vsako rotacijo/aktivacijo/umik,
  - auto-revoke pri sumljivih dogodkih (``revoke`` z razlogom).

Integracijski točki: ``auth_vault`` za shrambo (tukaj in-memory stanje) in
``audit_trail`` za sledljivost (tukaj interno audit seznam). Generator vrednosti
in ura sta vstavitveni točki — v testih deterministični.
"""

from __future__ import annotations

import secrets as pysecrets
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

DEFAULT_CLOCK: Callable[[], float] = time.time


def default_value_generator() -> str:
    """Privzeti generator: kriptografsko naključen token (URL-safe, 32 B)."""
    return pysecrets.token_urlsafe(32)


def _mask(value: Optional[str]) -> Optional[str]:
    """Maskiraj vrednost za odgovore: ``abcd…`` (nikoli polna skrivnost)."""
    if not value:
        return None
    return value[:4] + "…"


@dataclass
class SecretState:
    """Stanje ene skrivnosti v double-buffer življenjskem ciklu."""

    name: str
    kind: str
    rotation_interval_days: int
    active_value: str
    staged_value: Optional[str] = None
    passive_value: Optional[str] = None
    rotated_at: Optional[float] = None
    next_rotation_at: Optional[float] = None
    active: bool = True
    revoked: bool = False
    phase: str = "active"  # active | staged | passive | none


@dataclass
class AuditEntry:
    """Eden zapis v audit sled rotacij."""

    name: str
    action: str
    detail: str
    at: float


class SecretRotationManager:
    """Rotacija skrivnosti z double-buffer prehodom, schedulerjem in auditom."""

    def __init__(
        self,
        clock: Optional[Callable[[], float]] = None,
        value_generator: Optional[Callable[[], str]] = None,
    ):
        self._clock = clock or DEFAULT_CLOCK
        self._value_gen = value_generator or default_value_generator
        self.secrets: Dict[str, SecretState] = {}
        self.audit: List[AuditEntry] = []

    # ── Registracija ────────────────────────────────────────────────────────
    def register_secret(
        self,
        name: str,
        kind: str = "generic",
        rotation_interval_days: int = 30,
    ) -> SecretState:
        """Registriraj novo skrivnost; prva aktivna vrednost se generira takoj."""
        now = self._clock()
        state = SecretState(
            name=name,
            kind=kind,
            rotation_interval_days=rotation_interval_days,
            active_value=self._value_gen(),
            rotated_at=now,
            next_rotation_at=now + rotation_interval_days * 86400.0,
            phase="active",
        )
        self.secrets[name] = state
        self._audit(name, "register", f"kind={kind}, interval={rotation_interval_days}d", now)
        return state

    def _audit(self, name: str, action: str, detail: str, at: Optional[float] = None) -> None:
        self.audit.append(AuditEntry(name=name, action=action, detail=detail, at=at or self._clock()))

    # ── Rotacija (double buffer) ────────────────────────────────────────────
    def rotate(self, name: str) -> Optional[SecretState]:
        """Pripravi NOVO vrednost (staged) — stara ostaja aktivna (zero-downtime).

        Vrne stanje ali ``None`` (skrivnost ne obstaja / je umaknjena).
        """
        state = self.secrets.get(name)
        if state is None or state.revoked:
            return None
        now = self._clock()
        state.staged_value = self._value_gen()
        state.phase = "staged"
        self._audit(name, "rotate", "new value staged (double-buffer)", now)
        return state

    def activate(self, name: str) -> Optional[SecretState]:
        """Promoviraj staged → aktivna; prejšnja aktivna gre v pasivno.

        Zero-downtime preklop: aktivna vrednost se zamenja šele tukaj, ko je
        nova že pripravljena.
        """
        state = self.secrets.get(name)
        if state is None or state.revoked:
            return None
        if not state.staged_value:
            return state  # ni staged vrednosti → ni kaj aktivirati
        now = self._clock()
        state.passive_value = state.active_value   # stara → pasivna (rollback rezerva)
        state.active_value = state.staged_value    # nova → aktivna
        state.staged_value = None
        state.rotated_at = now
        state.next_rotation_at = now + state.rotation_interval_days * 86400.0
        state.phase = "active"
        self._audit(name, "activate", "staged promoted to active (zero-downtime)", now)
        return state

    # ── Scheduler / status / revoke ─────────────────────────────────────────
    def due_secrets(self, now: Optional[float] = None) -> List[SecretState]:
        """Skrivnosti, katerih rotacija je ZAPADLA (next_rotation_at <= now)."""
        current = now if now is not None else self._clock()
        return [
            s for s in self.secrets.values()
            if s.active and not s.revoked and s.next_rotation_at is not None
            and s.next_rotation_at <= current
        ]

    def status_of(self, name: str) -> Optional[SecretState]:
        return self.secrets.get(name)

    def all_statuses(self) -> List[SecretState]:
        return list(self.secrets.values())

    def revoke(self, name: str, reason: str) -> bool:
        """Takojšen umik (auto-revoke) — skrivnost je mrtva, rotacija ustavljena."""
        state = self.secrets.get(name)
        if state is None:
            return False
        state.revoked = True
        state.active = False
        state.phase = "none"
        self._audit(name, "revoke", f"reason={reason}", None)
        return True

    # ── Predstavitev (maskirano) ────────────────────────────────────────────
    def to_response(self, state: SecretState) -> Dict[str, Any]:
        """Stanje za API odgovor — vrednosti so vedno MASKIRANE."""
        return {
            "name": state.name,
            "kind": state.kind,
            "phase": state.phase,
            "active_value_masked": _mask(state.active_value),
            "rotated_at": _iso(state.rotated_at),
            "next_rotation_at": _iso(state.next_rotation_at),
            "active": state.active,
            "revoked": state.revoked,
        }


def _iso(ts: Optional[float]) -> Optional[str]:
    """Unix timestamp → ISO 8601 niz (UTC) za odgovore."""
    if ts is None:
        return None
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()
