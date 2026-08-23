"""Pydantic V2 schemas for config_manager."""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, ConfigDict, field_validator


class EnvSnapshot(BaseModel):
    """Validated view of a fully merged environment configuration.

    Strict mode: keys and values must be plain strings; anything else is
    rejected by the strict validator.
    """

    model_config = ConfigDict(strict=True)

    data: Dict[str, str]

    @field_validator("data")
    @classmethod
    def _validate_string_pairs(cls, v: Dict[str, str]) -> Dict[str, str]:
        for key, value in v.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValueError("env keys and values must be strings")
        return v


class EnvSourceModel(BaseModel):
    """Schema describing one .env-style source passed to ConfigManager."""

    model_config = ConfigDict(strict=True)

    content: str

    @field_validator("content")
    @classmethod
    def _validate_content(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("content must be a string")
        return v


__all__ = ["EnvSnapshot", "EnvSourceModel"]