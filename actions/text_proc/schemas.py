"""schemas.py — Pydantic V2 sheme za vhodne/izhodne podatke modula text_proc.

Opomba: jedro modula so čiste funkcije (tokenize/normalize/word_freq), zato
so sheme namenjene izključno (morebitni) FastAPI plasti, ne notranji logiki.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class TextInput(BaseModel):
    """Vhodna shema za obdelavo besedila."""

    text: str = Field(..., min_length=0, description="Vhodni niz za obdelavo.")

    @field_validator("text")
    @classmethod
    def text_must_be_str(cls, v: object) -> str:
        if not isinstance(v, str):
            raise ValueError("text mora biti niz (str)")
        return v


class TokenizeOutput(BaseModel):
    """Izhodna shema za tokenize."""

    tokens: List[str]


class NormalizeOutput(BaseModel):
    """Izhodna shema za normalize."""

    normalized: str


class WordFreqOutput(BaseModel):
    """Izhodna shema za word_freq."""

    word_freq: Dict[str, int]


class ProcessOutput(BaseModel):
    """Izhodna shema za kombinirano obdelavo."""

    normalized: str
    tokens: List[str]
    word_count: int
    word_freq: Dict[str, int]
    error: Optional[str] = None