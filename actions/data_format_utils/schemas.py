"""data_format_utils — Pydantic sheme (API plast)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CsvParseRequest(BaseModel):
    """Vhod za POST /csv-parse."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, description="CSV besedilo.")
    delimiter: str = Field(default=",", min_length=1, max_length=1)


class IsoParseRequest(BaseModel):
    """Vhod za POST /iso-parse."""

    value: str = Field(..., min_length=1, description="ISO 8601 datum YYYY-MM-DD.")


class DeepMergeRequest(BaseModel):
    """Vhod za POST /deep-merge."""

    model_config = ConfigDict(extra="forbid")

    a: Optional[Dict[str, Any]] = Field(default_factory=dict)
    b: Optional[Dict[str, Any]] = Field(default_factory=dict)


class DeepMergeResponse(BaseModel):
    merged: Dict[str, Any]


class DataFormatResponse(BaseModel):
    ok: bool
    result: Optional[Any] = None
