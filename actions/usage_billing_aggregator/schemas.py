"""usage_billing_aggregator — Pydantic sheme (API plast)."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class TariffRegisterRequest(BaseModel):
    """Vhod za POST /tariffs."""

    model_config = ConfigDict(extra="forbid")

    tenant: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    kind: Literal["metered", "tiered", "quota"] = "metered"
    unit_price: float = Field(default=0.0, ge=0)
    tier_limits: List[Optional[float]] = Field(default_factory=list)
    tier_prices: List[float] = Field(default_factory=list)
    quota_limit: float = Field(default=0.0, ge=0)
    monthly_fee: float = Field(default=0.0, ge=0)


class UsageRecordRequest(BaseModel):
    """Vhod za POST /usage."""

    model_config = ConfigDict(extra="forbid")

    tenant: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    units: float = Field(..., gt=0)


class UsageWindowRequest(BaseModel):
    """Vhod za GET /usage/{tenant}/{metric} — opcijsko okno (sekunde)."""

    window_seconds: Optional[float] = Field(default=None, gt=0)


class QuotaStatusResponse(BaseModel):
    tenant: str
    metric: str
    enforced: bool
    units: float
    limit: Optional[float] = None
    exceeded: Optional[bool] = None
    remaining: Optional[float] = None


class BillingSummaryResponse(BaseModel):
    tenant: str
    tariff: Optional[str] = None
    kind: Optional[str] = None
    cost: float
    details: Dict[str, float]


class AlertResponse(BaseModel):
    tenant: str
    metric: str
    units: float
    limit: float
    message: str
