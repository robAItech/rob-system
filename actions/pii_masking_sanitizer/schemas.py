"""pii_masking_sanitizer — Pydantic sheme (API plast)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from actions.pii_masking_sanitizer.pii import MASKS


class RegisterFieldRequest(BaseModel):
    """Vhod za POST /fields — registracija PII polja."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    strategy: str = Field(default="mask")


class MaskRequest(BaseModel):
    """Vhod za POST /mask — maskiraj JSON strukturo."""

    model_config = ConfigDict(extra="forbid")

    data: Dict[str, Any] = Field(..., description="Struktura s PII polji.")


class RedactRequest(BaseModel):
    """Vhod za POST /redact — redakcija prostega besedila."""

    text: str = Field(..., min_length=1)


class MaskResponse(BaseModel):
    masked: Dict[str, Any]


class RedactResponse(BaseModel):
    redacted: str
