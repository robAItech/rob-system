"""api_version_manager — Pydantic V2 sheme (API plast).

Življenjski cikel API verzij: SemVer oznake, deprecation politika, weighted
routing (canary/blue-green/A-B) in BC-break detekcija.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SemVerModel(BaseModel):
    """Strukturna SemVer verzija (major.minor.patch)."""

    model_config = ConfigDict(frozen=True)

    major: int = Field(..., ge=0)
    minor: int = Field(default=0, ge=0)
    patch: int = Field(default=0, ge=0)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def to_tag(self) -> str:
        """Oznaka ``v<major>`` — npr. 2.1.0 → v2."""
        return f"v{self.major}"

    @field_validator("major", "minor", "patch")
    @classmethod
    def _non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("version components must be >= 0")
        return value


class VersionRegisterRequest(BaseModel):
    """Vhod za POST /versions — registracija nove verzije s SemVer."""

    model_config = ConfigDict(extra="forbid")

    tag: str = Field(..., min_length=1, pattern=r"^v\d+$", description="Npr. v1, v2.")
    version: SemVerModel = Field(..., description="SemVer verzija (major.minor.patch).")
    weight: int = Field(default=100, ge=0, le=100, description="Teža za weighted routing.")
    active: bool = Field(default=True, description="Ali je verzija aktivna za routing?")


class VersionInfo(BaseModel):
    """Izhodna predstavitev verzije."""

    tag: str
    version: str
    weight: int
    active: bool
    deprecated: bool = False
    sunset: Optional[str] = None


class RouteVersion(BaseModel):
    """Ena verzija v weighted routing odločitvi."""

    tag: str = Field(..., min_length=1)
    weight: int = Field(..., ge=0, description="Teža (0–100; vsota ni nujno 100).")


class RouteRequest(BaseModel):
    """Vhod za POST /route — weighted izbor verzije (canary/A-B/blue-green)."""

    model_config = ConfigDict(extra="forbid")

    versions: List[RouteVersion] = Field(min_length=1, description="Kandidatke verzije s težami.")


class RouteResponse(BaseModel):
    """Izhod POST /route: izbrana verzija + deprecation opozorila."""

    selected: str
    version: str
    deprecation_warnings: List[str] = Field(default_factory=list)


class DeprecationRequest(BaseModel):
    """Vhod za POST /versions/{tag}/deprecate."""

    sunset: Optional[str] = Field(None, description="ISO datum prenehanja (npr. 2027-01-01).")
    notice: str = Field(..., min_length=1, description="Obvestilo za integratorje.")


class BreakingCheckRequest(BaseModel):
    """Vhod za POST /check-bc — BC-break detekcija med dvema JSON shemama."""

    model_config = ConfigDict(extra="forbid")

    old_schema: Dict[str, Any] = Field(..., description="Prejšnja JSON Schema (object).")
    new_schema: Dict[str, Any] = Field(..., description="Nova JSON Schema (object).")


class BreakingCheckResponse(BaseModel):
    """Izhod BC-break analize: ali je sprememba prelomna + changelog."""

    is_breaking: bool
    changes: List[str] = Field(default_factory=list)
