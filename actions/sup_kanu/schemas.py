"""Pydantic V2 sheme za spletno stran modula sup_kanu.

Arhitekturna usmeritev:
  - sheme: Pydantic V2 s strogimi validatorji (extra="forbid", validacije vrednosti).
"""

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Duration = Literal["1h", "2h", "dan"]


class PriceEntry(BaseModel):
    """Cena izposoje za eno trajanje (1h / 2h / dan)."""

    model_config = ConfigDict(extra="forbid")

    duration: Duration
    price_eur: float = Field(gt=0)

    @field_validator("price_eur")
    @classmethod
    def _price_must_be_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("price_eur mora biti večji od 0")
        return round(float(value), 2)


class PriceRow(BaseModel):
    """Vrstica cen za eno vrsto izposoje (npr. SUP deska)."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    prices: List[PriceEntry] = Field(min_length=1)

    @field_validator("label")
    @classmethod
    def _label_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("label ne sme biti prazen")
        return value.strip()


class ContactInfo(BaseModel):
    """Kontaktni podatki podjetja."""

    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=3)
    phone: str = Field(min_length=3)
    email: str = Field(min_length=3)

    @field_validator("email")
    @classmethod
    def _email_must_be_valid(cls, value: str) -> str:
        value = value.strip()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("email ni veljaven")
        return value


class OpeningHours(BaseModel):
    """Odpiralni čas za en dan / obdobje."""

    model_config = ConfigDict(extra="forbid")

    day: str = Field(min_length=2)
    hours: str = Field(min_length=1)

    @field_validator("day", "hours")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("polje ne sme biti prazno")
        return value.strip()


class SiteContent(BaseModel):
    """Celotna vsebina spletne strani SUP Kanu Ljubljanica."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3)
    about: str = Field(min_length=20)
    offers: List[str] = Field(min_length=3)
    prices: List[PriceRow] = Field(min_length=1)
    contact: ContactInfo
    opening_hours: List[OpeningHours] = Field(min_length=1)
    gallery: List[str] = Field(min_length=1)

    @field_validator("title", "about", "offers", "gallery")
    @classmethod
    def _text_not_blank(cls, value):
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not str(item).strip():
                raise ValueError("besedilo ne sme biti prazno")
        return value
