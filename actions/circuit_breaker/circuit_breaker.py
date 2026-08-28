"""circuit_breaker — FASADA nad actions.resilience_core (Refaktor 1).

Logika circuit breakerja je konsolidirana v ``resilience_core``; ta modul
ostaja kot stabilen javni API (re-export) za obstoječe uporabnike/runtime.
"""

from actions.resilience_core.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitState,
    CircuitConfig,
)

__all__ = ["CircuitBreaker", "CircuitBreakerOpenException", "CircuitState", "CircuitConfig"]
