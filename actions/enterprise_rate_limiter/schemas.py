from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class RateLimitConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    max_requests: int = Field(default=5, ge=1)
    window_seconds: float = Field(default=1.0, gt=0)

class RateLimitRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Client IP or API Key")

class RateLimitResponse(BaseModel):
    key: str
    allowed: bool
    remaining: int
    reset_in_seconds: float
