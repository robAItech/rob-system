"""Pydantic V2 Schemas — vhodni in izhodni modeli API-ja truncate_text."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TruncateRequest(BaseModel):
    """Zahteva za skrajšanje niza (stroga validacija)."""

    model_config = ConfigDict(strict=True)

    niz: str = Field(..., description="Vhodni niz, ki ga želimo skrajšati")
    max_len: int = Field(80, ge=0, description="Največja dovoljena dolžina rezultata")
    suffix: str = Field("...", description="Niz, dodan na konec skrajšanega rezultata")

    @field_validator("max_len")
    @classmethod
    def _max_len_mora_biti_nenegativen(cls, v: int) -> int:
        if v < 0:
            raise ValueError("max_len ne sme biti negativen")
        return v


class TruncateResponse(BaseModel):
    """Odziv API-ja truncate_text."""

    model_config = ConfigDict(strict=True)

    result: str = Field(..., description="Skrajšan (ali nespremenjen) niz")
    truncated: bool = Field(..., description="Ali je bil niz dejansko skrajšan")
    original_length: int = Field(..., ge=0, description="Dolžina originalnega niza")