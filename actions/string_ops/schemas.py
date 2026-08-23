"""Pydantic V2 sheme — strogi validatorji za HTTP vmesnik modula string_ops."""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, Field, field_validator


class _StringModel(BaseModel):
    """Skupna osnova: polje ``text``, ki mora biti strogo ``str``."""

    text: str = Field(..., description="Vhodni niz za obdelavo.")

    @field_validator("text")
    @classmethod
    def _text_mora_biti_str(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("text mora biti str")
        return v


class SlugRequest(_StringModel):
    """Vhod za ``slug``."""


class SlugResponse(BaseModel):
    slug: str


class TruncateRequest(_StringModel):
    """Vhod za ``truncate``."""

    max_len: int = Field(80, ge=0, description="Največja dolžina rezultata.")
    suffix: str = Field("...", description="Pripona ob skrajšanju.")


class TruncateResponse(BaseModel):
    result: str


class TruncateStartRequest(_StringModel):
    """Vhod za ``truncate_start``."""

    max_len: int = Field(80, ge=0, description="Največja dolžina rezultata.")
    prefix: str = Field("...", description="Predpona ob skrajšanju.")


class TruncateStartResponse(BaseModel):
    result: str


class TokenizeRequest(_StringModel):
    """Vhod za ``tokenize``."""


class TokenizeResponse(BaseModel):
    words: List[str]


class NormalizeRequest(_StringModel):
    """Vhod za ``normalize``."""


class NormalizeResponse(BaseModel):
    result: str


class WordFreqRequest(_StringModel):
    """Vhod za ``word_freq``."""


class WordFreqResponse(BaseModel):
    frequencies: Dict[str, int]
