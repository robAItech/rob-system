"""resilience_core — FastAPI aplikacija (API plast, Refaktor 1).

Expose: enotna politika odpornosti (rate-limit → circuit → retry) prek
``POST /apply`` + health. Exporta ``app`` — v runtime pod
``/api/resilience_core/*``.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from actions.resilience_core.resilience import (
    CircuitBreakerOpenException,
    ResilienceExecutor,
    ResiliencePolicyConfig,
)
from actions.resilience_core.schemas import (
    ResiliencePolicyRequest,
    ResiliencePolicyResponse,
)

app = FastAPI(title="Rob AI Studio - Resilience Core", version="1.0.0")
executor = ResilienceExecutor(
    ResiliencePolicyConfig(rate_limit_max=10, rate_limit_window=5.0)
)


@app.post("/apply", response_model=ResiliencePolicyResponse)
async def apply_policy(body: ResiliencePolicyRequest) -> JSONResponse:
    """Izvedi nalogo skozi enotno politiko (rate-limit → circuit → retry)."""

    async def task() -> Dict[str, Any]:
        if body.should_fail:
            raise ValueError("Downstream error")
        return {"status": "SUCCESS", "payload": body.payload}

    try:
        result = await executor.execute(body.key, body.service_name, task)
        return JSONResponse(
            ResiliencePolicyResponse(
                status="OK",
                result=result,
                circuit_state=executor._circuit(body.service_name).state,
            ).model_dump()
        )
    except CircuitBreakerOpenException as exc:
        return JSONResponse(status_code=429, content={"error": str(exc), "status": "BLOCKED"})
    except ValueError as exc:
        return JSONResponse(status_code=500, content={"error": str(exc), "status": "FAILED"})


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return {
        "status": "UP",
        "circuits": list(executor.circuits.keys()),
        "rate_limit_keys": len(executor.limit._windows) + len(executor.limit._buckets),
    }
