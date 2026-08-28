"""secret_rotation — Pydantic V2 sheme (API plast).

Avtomatizirana rotacija skrivnosti (API ključi, DB gesla, certifikati) brez
downtime: double-buffer (aktivna → pripravljena → pasivna), scheduler (due) in
audit sled za vsako rotacijo. Skrivnosti se v odgovorih vedno maskirajo.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

#: Vrste skrivnosti, ki jih podpira rotacija.
SecretKind = Literal["api_key", "db_password", "certificate", "generic"]

#: Faze double-buffer prehoda.
SecretPhase = Literal["active", "staged", "passive", "none"]


class SecretRegisterRequest(BaseModel):
    """Vhod za POST /secrets — registracija nove skrivnosti z rotacijsko politiko."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, pattern=r"^[A-Za-z0-9_.-]+$", description="Unikatno ime skrivnosti.")
    kind: SecretKind = Field(default="generic", description="Vrsta skrivnosti.")
    rotation_interval_days: int = Field(default=30, ge=1, le=3650, description="Interval rotacije v dneh.")


class SecretStatusResponse(BaseModel):
    """Izhodna predstavitev stanja skrivnosti (vrednosti so MASKIRANE)."""

    name: str
    kind: SecretKind
    phase: SecretPhase
    active_value_masked: Optional[str] = None
    rotated_at: Optional[str] = None
    next_rotation_at: Optional[str] = None
    active: bool
    revoked: bool = False


class RotationRequest(BaseModel):
    """Vhod za POST /rotate — pripravi novo vrednost (staged)."""

    name: str = Field(..., min_length=1)


class RotationResponse(BaseModel):
    """Izhod rotacije/aktivacije."""

    name: str
    action: Literal["rotated", "activated"]
    next_rotation_at: Optional[str] = None


class RevokeRequest(BaseModel):
    """Vhod za POST /revoke — takojšen umik skrivnosti (auto-revoke)."""

    name: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class AuditEntryResponse(BaseModel):
    """En vnos v audit sled rotacij."""

    name: str
    action: str
    detail: str
    at: str
