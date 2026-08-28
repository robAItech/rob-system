"""circuit_breaker — Pydantic sheme (fasada nad resilience_core.schemas).

``CircuitState``/``CircuitConfig`` sta konsolidirana v ``resilience_core``;
tu sta re-exportana, da ostane pogodba nespremenjena.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any

from actions.resilience_core.schemas import CircuitState, CircuitConfig

__all__ = ["CircuitState", "CircuitConfig"]


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
