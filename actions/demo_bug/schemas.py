# Pydantic V2 Schemas
from pydantic import BaseModel, Field, field_validator


class DivideRequest(BaseModel):
    """Zahtevek za deljenje dveh števil."""
    a: float = Field(..., description="Prvo število (deljenec)")
    b: float = Field(..., description="Drugo število (delitelj)")

    @field_validator("b")
    @classmethod
    def validate_b_not_zero(cls, v: float) -> float:
        """Validator, ki prepreči deljenje z nič na nivoju sheme."""
        if v == 0:
            raise ValueError("deljenje z nič ni dovoljeno")
        return v


class DivideResponse(BaseModel):
    """Odgovor z rezultatom deljenja."""
    result: float = Field(..., description="Rezultat deljenja")