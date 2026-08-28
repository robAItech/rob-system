"""Pydantic V2 sheme za modul iso8601_util.

Sheme uporabljajo stroge validatorje (mode="before" + ročno preverjanje
formata), da se neveljavni vnosi zavrnejo že pred klicem jedra.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from .core import format_iso, parse_iso


class IsoDateRequest(BaseModel):
    """Vhod za razčlenjevanje: ISO 8601 datum (YYYY-MM-DD)."""

    model_config = ConfigDict(extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _validate_iso_date(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("value mora biti niz")
        try:
            parse_iso(value)
        except ValueError as exc:
            raise ValueError(f"neveljaven ISO 8601 datum: {exc}") from None
        return value


class IsoDateTimeRequest(BaseModel):
    """Vhod za oblikovanje: ISO 8601 datum ali datum-čas (YYYY-MM-DD[THH:MM:SS])."""

    model_config = ConfigDict(extra="forbid")

    value: str

    @field_validator("value")
    @classmethod
    def _validate_datetime(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("value mora biti niz")
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"neveljaven ISO 8601 datum-čas: {exc}") from None
        return value


class IsoDateResponse(BaseModel):
    """Odgovor: ISO 8601 niz (polnočni datetime za parse, datum za format)."""

    model_config = ConfigDict(extra="forbid")

    value: str