"""webhook_dispatcher — FastAPI aplikacija (API plast).

Expose: registracija subscriberjev, dostava dogodkov, DLQ in health.
Exporta ``app`` (FastAPI) — ob montaži v actions runtime se nahaja pod
``/api/webhook_dispatcher/*``; standalone pod ``uvicorn actions.webhook_dispatcher.main:app``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from actions.webhook_dispatcher.schemas import (
    DeadLetterEntry,
    DispatchResponse,
    WebhookEventPayload,
    WebhookRegisterRequest,
    WebhookSubscriberResponse,
)
from actions.webhook_dispatcher.webhook_dispatcher import WebhookDispatcher, WebhookEvent

app = FastAPI(title="Rob AI Studio - Webhook Dispatcher", version="1.0.0")
dispatcher = WebhookDispatcher()


def _subscriber_out(sub) -> WebhookSubscriberResponse:
    """Predstavi subscriberja brez razkritja secret-a."""
    return WebhookSubscriberResponse(
        id=sub.id,
        url=sub.url,
        events=list(sub.events),
        max_attempts=sub.max_attempts,
        base_delay_seconds=sub.base_delay_seconds,
        active=sub.active,
        has_secret=bool(sub.secret),
    )


@app.post("/subscribers", response_model=WebhookSubscriberResponse)
async def register_subscriber(body: WebhookRegisterRequest) -> JSONResponse:
    """Registriraj webhook subscriberja."""
    sub = dispatcher.register_subscriber(
        url=body.url,
        secret=body.secret,
        events=body.events,
        max_attempts=body.max_attempts,
        base_delay_seconds=body.base_delay_seconds,
        active=body.active,
    )
    return JSONResponse(_subscriber_out(sub).model_dump())


@app.get("/subscribers", response_model=List[WebhookSubscriberResponse])
async def list_subscribers() -> JSONResponse:
    """Seznam vseh subscriberjev (secret je redacted)."""
    return JSONResponse([_subscriber_out(s).model_dump() for s in dispatcher.subscribers.values()])


@app.delete("/subscribers/{subscriber_id}")
async def unregister_subscriber(subscriber_id: str) -> JSONResponse:
    """Odstrani subscriberja; 404, če ne obstaja."""
    if not dispatcher.unregister_subscriber(subscriber_id):
        raise HTTPException(status_code=404, detail="subscriber not found")
    return JSONResponse({"subscriber_id": subscriber_id, "removed": True})


@app.post("/dispatch", response_model=DispatchResponse)
async def dispatch(body: WebhookEventPayload) -> JSONResponse:
    """Dostavi dogodek vsem naročenim subscriberjem (HMAC + idempotency + DLQ)."""
    # Idempotency ključ: uporabnikov, sicer auto-generiran v WebhookEvent.
    event = WebhookEvent(
        type=body.type,
        payload=body.payload,
        event_id=body.event_id if body.event_id else None,
    )
    results = await dispatcher.dispatch_event(event)
    return JSONResponse(
        {
            "event_id": event.event_id,
            "type": event.type,
            "results": [
                {
                    "event_id": r.event_id,
                    "subscriber_id": r.subscriber_id,
                    "status": r.status,
                    "attempts": r.attempts,
                    "error": r.error,
                }
                for r in results
            ],
        }
    )


@app.get("/dead-letter", response_model=List[DeadLetterEntry])
async def dead_letter() -> JSONResponse:
    """Vsebina dead-letter queue (neponovljive napake)."""
    return JSONResponse(dispatcher.dead_letter)


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return await dispatcher.health_check()
