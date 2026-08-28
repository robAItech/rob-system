"""telemetry_bus — FastAPI aplikacija (API plast, Refaktor 2).

Expose: objava dogodkov (POST /publish), pregled (GET /events, /stats) in
health. Exporta ``app`` — v runtime pod ``/api/telemetry_bus/*``.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from actions.telemetry_bus.schemas import (
    PublishRequest,
    TelemetryEventResponse,
    TelemetryStatsResponse,
)
from actions.telemetry_bus.telemetry import TelemetryBus

app = FastAPI(title="Rob AI Studio - Telemetry Bus", version="1.0.0")
bus = TelemetryBus()


@app.post("/publish", response_model=TelemetryEventResponse)
async def publish(body: PublishRequest) -> JSONResponse:
    """Objavi dogodek na korelacijskem vodilu (razpošlje sink-e + transport)."""
    event = await bus.publish(body.type, body.payload, body.correlation_id)
    return JSONResponse(
        TelemetryEventResponse(
            event_id=event.event_id,
            type=event.type,
            correlation_id=event.correlation_id,
            payload=event.payload,
        ).model_dump()
    )


@app.get("/events", response_model=list[TelemetryEventResponse])
async def events() -> JSONResponse:
    """Zgodovina dogodkov (observability)."""
    return JSONResponse(
        [
            TelemetryEventResponse(
                event_id=e.event_id,
                type=e.type,
                correlation_id=e.correlation_id,
                payload=e.payload,
            ).model_dump()
            for e in bus.events
        ]
    )


@app.get("/stats", response_model=TelemetryStatsResponse)
async def stats() -> JSONResponse:
    """Agregirana statistika dogodkov."""
    return JSONResponse(TelemetryStatsResponse(**bus.stats()).model_dump())


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return {"status": "UP", "events": len(bus.events)}
