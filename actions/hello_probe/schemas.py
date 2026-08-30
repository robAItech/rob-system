"""Pydantic V2 sheme za hello_probe."""

from pydantic import BaseModel, Field, field_validator


class GreetRequest(BaseModel):
    """Zahtevek za pozdrav z obveznim, nepraznim imenom."""

    name: str = Field(min_length=1, max_length=200, description="Ime osebe.")

    @field_validator("name")
    @classmethod
    def _name_must_be_nonblank(cls, value: str) -> str:
        """Odstrani robne presledke in zavrni prazno ime.

        Vedno vrne validirano vrednost polja (nikoli None/False).
        """
        value = value.strip()
        if not value:
            raise ValueError("ime ne sme biti prazno")
        return value