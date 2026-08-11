from pydantic import BaseModel, Field, ConfigDict, HttpUrl
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

class WebhookStatus(str, Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"

class WebhookEndpoint(BaseModel):
    id: str = Field(..., min_length=1)
    url: str = Field(..., description="Target URL for the webhook")
    secret: str = Field(..., min_length=16, description="Secret used to sign the HMAC-SHA256 payload")
    max_retries: int = Field(default=3, ge=0)

class WebhookEvent(BaseModel):
    event_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class DeliveryAttempt(BaseModel):
    attempt_number: int
    status_code: Optional[int]
    success: bool
    error: Optional[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class DeliveryResult(BaseModel):
    event_id: str
    endpoint_id: str
    status: WebhookStatus
    attempts: List[DeliveryAttempt] = Field(default_factory=list)
