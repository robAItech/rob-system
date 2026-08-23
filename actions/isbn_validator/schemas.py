"""actions/isbn_validator/schemas.py — Pydantic V2 schemas (strict mode)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ISBNValidationRequest(BaseModel):
    """Strict request payload: the ISBN string to validate."""

    model_config = ConfigDict(strict=True)

    isbn: str = Field(
        ...,
        description="ISBN-10 or ISBN-13 string (leading/trailing whitespace is stripped)",
    )

    @field_validator("isbn")
    @classmethod
    def _strip_whitespace(cls, value: str) -> str:
        return value.strip()


class ISBNValidationResponse(BaseModel):
    """Response payload: validation result."""

    model_config = ConfigDict(strict=True)

    isbn: str
    is_valid: bool
