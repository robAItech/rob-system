"""schemas.py — Pydantic V2 sheme za actions.config_loader API."""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field


class ParseEnvRequest(BaseModel):
    """Telo zahteve za razčlenjevanje .env vsebine."""

    model_config = ConfigDict(strict=True, extra="forbid")

    text: str = Field(..., description="Surova .env vsebina (niz).")


class ParseIniRequest(BaseModel):
    """Telo zahteve za razčlenjevanje INI vsebine."""

    model_config = ConfigDict(strict=True, extra="forbid")

    text: str = Field(..., description="Surova INI vsebina (niz).")


class ParseResponse(BaseModel):
    """Odziv z razčlenjenim slovarjem."""

    model_config = ConfigDict(strict=True)

    data: Dict[str, Any] = Field(..., description="Razčlenjen slovar.")