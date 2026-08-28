"""webhook_dispatcher — Pydantic V2 sheme (API plast).

Enterprise B2B dostava dogodkov: subscriber registracija, dogodek za dostavo in
izhodne strukture (DeliveryResult, health). Stroga validacija vhoda.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Statusi dostave (consistent z domensko logiko).
DeliveryStatus = Literal["delivered", "retrying", "dead", "skipped"]


class WebhookRegisterRequest(BaseModel):
    """Vhod za POST /subscribers — registracija novega webhook subscriberja."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(..., min_length=1, description="Ciljni endpoint (http/https).")
    secret: str = Field(..., min_length=8, description="HMAC-SHA256 deljeni skrivni ključ.")
    events: List[str] = Field(
        default_factory=list,
        description="Naročeni tipi dogodkov (``*`` = vsi).",
    )
    max_attempts: int = Field(default=3, ge=1, le=10, description="Število poskusov dostave.")
    base_delay_seconds: float = Field(
        default=0.5, gt=0, le=60, description="Začetni zamik eksponentnega backoffa."
    )
    active: bool = Field(default=True, description="Je subscriber aktiviran?")

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, value: str) -> str:
        """Samo http/https — prepreči SSRF-style schème (file://, ftp://, ...)."""
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return value


class WebhookSubscriberResponse(BaseModel):
    """Izhodna predstavitev subscriberja (brez razkritja secret-a)."""

    model_config = ConfigDict(extra="allow")

    id: str
    url: str
    events: List[str]
    max_attempts: int
    base_delay_seconds: float
    active: bool
    # Secret se NIKOLI ne vrača v odgovorih — le prisotnost zaznamuje (redacted).
    has_secret: bool = True


class WebhookEventPayload(BaseModel):
    """Dogodek za dostavo: tip + poljuben strukturni payload."""

    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1, description="Tip dogodka (npr. invoice.paid).")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Poljuben JSON payload.")
    event_id: Optional[str] = Field(
        default=None, description="Idempotency ključ; auto-generiran, če manjka."
    )


class DispatchResponse(BaseModel):
    """Izhod POST /dispatch — rezultati dostave za vse naročene subscriberje."""

    event_id: str
    type: str
    results: List[Dict[str, Any]]


class DeadLetterEntry(BaseModel):
    """Vnos v dead-letter queue (neponovljive napake)."""

    event_id: str
    subscriber_id: str
    url: str
    status: DeliveryStatus
    attempts: int
    error: str
