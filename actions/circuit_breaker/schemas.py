from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from enum import Enum

class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    failure_threshold: int = Field(default=3, ge=1)
    recovery_timeout: float = Field(default=0.2, gt=0)
    half_open_success_threshold: int = Field(default=2, ge=1)

class ExecutionRequest(BaseModel):
    service_name: str = Field(..., min_length=1)
    should_fail: bool = Field(default=False)
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)

class CircuitStatusResponse(BaseModel):
    service_name: str
    state: CircuitState
    failure_count: int
    success_count: int
    total_requests: int
