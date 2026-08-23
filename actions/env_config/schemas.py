"""Pydantic V2 sheme za env_config API (striktna validacija)."""

from typing import Dict

from pydantic import BaseModel, Field, field_validator


class EnvParseRequest(BaseModel):
    """Zahteva za razčlenjevanje .env vsebine."""

    text: str = Field(..., description="Vsebina .env datoteke (niz).")

    @field_validator("text")
    @classmethod
    def text_must_be_string(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("text mora biti niz (str)")
        return value


class EnvLoadRequest(BaseModel):
    """Zahteva za branje .env datoteke."""

    path: str = Field(..., min_length=1, description="Pot do .env datoteke.")

    @field_validator("path")
    @classmethod
    def path_must_not_be_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("path ne sme biti prazen")
        return value


class EnvParseResponse(BaseModel):
    """Odgovor API-ja: razčlenjen slovar + število vnosov."""

    data: Dict[str, str] = Field(..., description="Razčlenjen slovar .env vnosov.")
    count: int = Field(..., ge=0, description="Število vnosov.")