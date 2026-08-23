"""Pydantic V2 sheme za ``csv_parser`` API."""

from typing import List

from pydantic import BaseModel, Field, field_validator


class CSVParseRequest(BaseModel):
    """Zahtevek za razčlenjevanje CSV besedila."""

    text: str
    delimiter: str = Field(default=",", description="Ločilni znak (natanko en znak).")

    @field_validator("delimiter")
    @classmethod
    def _delimiter_must_be_single_char(cls, value: str) -> str:
        """Strog validator: delimiter mora biti natanko en znak."""
        if not isinstance(value, str) or len(value) != 1:
            raise ValueError("delimiter mora biti natanko en znak")
        return value


class CSVParseResponse(BaseModel):
    """Odgovor: seznam razčlenjenih vrstic."""

    rows: List[List[str]]


class CSVToCsvRequest(BaseModel):
    """Zahtevek za serializacijo vrstic nazaj v CSV besedilo."""

    rows: List[List[str]]
    delimiter: str = Field(default=",", description="Ločilni znak (natanko en znak).")

    @field_validator("delimiter")
    @classmethod
    def _delimiter_must_be_single_char(cls, value: str) -> str:
        """Strog validator: delimiter mora biti natanko en znak."""
        if not isinstance(value, str) or len(value) != 1:
            raise ValueError("delimiter mora biti natanko en znak")
        return value


class CSVToCsvResponse(BaseModel):
    """Odgovor: serializirano CSV besedilo."""

    text: str