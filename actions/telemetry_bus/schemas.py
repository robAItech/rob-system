"""telemetry_bus — Pydantic sheme (API plast)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class PublishRequest(BaseModel):
    """Vhod za POST /publish."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1, description="Tip dogodka (npr. invoice.paid).")
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = Field(default=None)


class TelemetryEventResponse(BaseModel):
    """Izhodna predstavitev dogodka."""

    event_id: str
    type: str
    correlation_id: str
    payload: Dict[str, Any]


class TelemetryStatsResponse(BaseModel):
    total: int
    by_type: Dict[str, int]
