"""api_version_manager — jedro domenske logike: življenjski cikel API verzij.

Kot predlaga arhitekturna revizija (3.2): upravljanje SemVer verzij, deprecation
politik (Deprecation/Sunset headerji), weighted traffic routing (canary,
blue/green, A/B) in samodejna BC-break detekcija ob prelomni spremembi sheme.

Stanje je v spominu (mono-repo testno okolje). Vse odločitve so deterministične
z injiciranim ``rng`` (``random.random``) — v testih fiksna vrednost.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SemVer:
    """SemVer 2.0.0 jedro: major.minor.patch s primerjavo in parsanjem."""

    major: int
    minor: int = 0
    patch: int = 0

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        """Parsaj ``1.2.3`` ali ``v1.2.3`` (poišče prve 3 številčne segmente)."""
        cleaned = value.strip()
        if cleaned.startswith("v"):
            cleaned = cleaned[1:]
        parts = cleaned.split(".")
        if len(parts) not in (1, 2, 3) or not all(p.isdigit() for p in parts):
            raise ValueError(f"invalid SemVer: {value!r}")
        nums = [int(p) for p in parts]
        nums += [0] * (3 - len(nums))
        return cls(major=nums[0], minor=nums[1], patch=nums[2])

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def to_tag(self) -> str:
        return f"v{self.major}"

    def __lt__(self, other: "SemVer") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def is_compatible_with(self, other: "SemVer") -> bool:
        """BC: sprememba major → prelomna; minor/patch → kompatibilno."""
        return self.major == other.major


@dataclass
class VersionRoute:
    """Registrirana verzija: tag, SemVer, teža, deprecation stanje."""

    tag: str
    version: SemVer
    weight: int = 100
    active: bool = True
    deprecated: bool = False
    sunset: Optional[str] = None
    notice: Optional[str] = None


class VersionManager:
    """Registracija verzij, weighted routing, deprecation, BC-break analiza."""

    def __init__(self, rng: Optional[Callable[[], float]] = None):
        self._rng: Callable[[], float] = rng or random.random
        self.versions: Dict[str, VersionRoute] = {}

    # ── Registracija ────────────────────────────────────────────────────────
    def register_version(
        self,
        tag: str,
        version: SemVer,
        weight: int = 100,
        active: bool = True,
    ) -> VersionRoute:
        """Registriraj verzijo pod oznako (tag)."""
        route = VersionRoute(tag=tag, version=version, weight=weight, active=active)
        self.versions[tag] = route
        return route

    def list_versions(self) -> List[VersionRoute]:
        return sorted(self.versions.values(), key=lambda v: v.version)

    def get(self, tag: str) -> Optional[VersionRoute]:
        return self.versions.get(tag)

    # ── Deprecation ─────────────────────────────────────────────────────────
    def deprecate(self, tag: str, notice: str, sunset: Optional[str] = None) -> bool:
        """Označi verzijo kot deprecirano (Sunset + obvestilo)."""
        route = self.versions.get(tag)
        if route is None:
            return False
        route.deprecated = True
        route.notice = notice
        route.sunset = sunset
        return True

    def active_deprecations(self) -> List[VersionRoute]:
        return [v for v in self.versions.values() if v.deprecated]

    def deprecation_headers(self, tag: str) -> List[str]:
        """``Deprecation: true`` + ``Sunset: <datum>`` — za HTTP odgovore."""
        route = self.versions.get(tag)
        if route is None or not route.deprecated:
            return []
        headers = ["Deprecation: true"]
        if route.sunset:
            headers.append(f"Sunset: {route.sunset}")
        if route.notice:
            headers.append(f"Warning: 299 - {route.notice}")
        return headers

    # ── Weighted routing ────────────────────────────────────────────────────
    def route(self, targets: List[Tuple[str, int]]) -> Optional[Tuple[str, SemVer]]:
        """Weighted izbor med kandidatkami (canary/blue-green/A-B).

        Vrne (tag, version) ali ``None``, če ni aktivne kandidatke s težo > 0.
        """
        active = [(tag, w) for tag, w in targets if self.versions.get(tag) and self.versions[tag].active and w > 0]
        if not active:
            return None
        total = sum(w for _, w in active)
        roll = self._rng() * total
        cumulative = 0.0
        for tag, w in active:
            cumulative += w
            if roll < cumulative:
                return tag, self.versions[tag].version
        tag, _ = active[-1]
        return tag, self.versions[tag].version

    # ── BC-break detekcija ──────────────────────────────────────────────────
    @staticmethod
    def detect_breaking_change(old: Dict[str, Any], new: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Primerjaj dve JSON shemi → (is_breaking, changelog).

        Prelomno: odstranjen obvezen atribut, spremenjen tip atributa, odstranjena
        celotna property-ja. Aditivno (neprelomno): dodani novi atributi.
        """
        breaking: List[str] = []
        non_breaking: List[str] = []
        old_props: Dict[str, Any] = (old.get("properties") or {}) if isinstance(old, dict) else {}
        new_props: Dict[str, Any] = (new.get("properties") or {}) if isinstance(new, dict) else {}
        old_required: List[str] = (old.get("required") or []) if isinstance(old, dict) else []
        new_required: List[str] = (new.get("required") or []) if isinstance(new, dict) else []

        for req in old_required:
            if req not in new_required:
                breaking.append(f"REQUIRED field '{req}' removed from required list")
            if req not in new_props:
                breaking.append(f"REQUIRED field '{req}' removed entirely")

        for name, old_spec in old_props.items():
            if name not in new_props:
                breaking.append(f"field '{name}' removed")
                continue
            new_spec = new_props[name]
            old_type = old_spec.get("type") if isinstance(old_spec, dict) else None
            new_type = new_spec.get("type") if isinstance(new_spec, dict) else None
            if old_type and new_type and old_type != new_type:
                breaking.append(f"field '{name}' type changed: {old_type} → {new_type}")

        for name in new_props:
            if name not in old_props:
                non_breaking.append(f"field '{name}' added (additive, non-breaking)")

        # Prelomno je le, če obstaja kakšna BREAKING sprememba (aditivno ni).
        return bool(breaking), breaking + non_breaking
