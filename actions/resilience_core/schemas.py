"""resilience_core — Pydantic sheme (API plast).

Re-exportuje tudi ``CircuitState``/``CircuitConfig``, da fasade
(``circuit_breaker.schemas``) ostanejo enoten vir brez duplikacije logike.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from actions.resilience_core.resilience import CircuitState, CircuitConfig

#: Re-export za backward-compat (nekoč actions.circuit_breaker.schemas).
__all__ = ["CircuitState", "CircuitConfig"]


class ResiliencePolicyRequest(BaseModel):
    """Vhod za POST /apply — izvedba naloge skozi enotno politiko."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1, description="Rate-limit ključ (npr. client IP).")
    service_name: str = Field(..., min_length=1, description="Circuit breaker storitev.")
    should_fail: bool = Field(default=False, description="Simuliraj napako (test).")
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ResiliencePolicyResponse(BaseModel):
    """Izhod POST /apply: rezultat + status politike."""

    status: str
    result: Optional[Dict[str, Any]] = None
    circuit_state: Optional[CircuitState] = None
