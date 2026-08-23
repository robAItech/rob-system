"""ini_config — Pydantic V2 schemas.

Strict models used by the FastAPI layer to validate requests and shape
responses. Validators reject empty/whitespace-only input and forbid unknown
fields so contract violations fail fast.
"""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = ["IniSection", "IniDocument", "ParseRequest"]


class IniSection(BaseModel):
    """One INI section: a mapping of keys to string values."""

    model_config = ConfigDict(extra="forbid")

    values: Dict[str, str] = Field(
        default_factory=dict,
        description="Key/value pairs belonging to the section.",
    )


class IniDocument(BaseModel):
    """The full parsed INI document: sections -> IniSection."""

    model_config = ConfigDict(extra="forbid")

    sections: Dict[str, IniSection] = Field(
        default_factory=dict,
        description="Section name -> section content.",
    )


class ParseRequest(BaseModel):
    """Request body for ``POST /ini-config/parse``."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Raw INI text to parse.")

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("text must not be empty")
        return value