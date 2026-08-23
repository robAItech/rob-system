"""Pydantic V2 Schemas — strict validators for the slugify API."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SlugifyRequest(BaseModel):
    """Request payload: the raw string to convert into a URL slug."""

    model_config = ConfigDict(strict=True, extra="forbid")

    text: str = Field(..., description="Input string to convert into a URL slug")

    @field_validator("text")
    @classmethod
    def text_must_be_string(cls, value: object) -> str:
        # strict=True already enforces str; this validator documents the rule
        # and rejects any non-string value that slips through.
        if not isinstance(value, str):
            raise ValueError("text must be a string")
        return value


class SlugifyResponse(BaseModel):
    """Response payload: the generated URL slug."""

    model_config = ConfigDict(strict=True)

    slug: str = Field(..., description="URL-safe slug")


__all__ = ["SlugifyRequest", "SlugifyResponse"]