"""Pytest test suite za actions/webhook_dispatcher.

Deterministično (brez omrežja, brez realnih sleep): transport nadomesti
``FakeDriver``, backoff ``FakeSleeper``. Preveri: HMAC podpis/verifikacija,
registracijo, retry + DLQ, idempotency, deaktivacijo mrtvih in FastAPI plast.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from actions.webhook_dispatcher.main import app, dispatcher
from actions.webhook_dispatcher.webhook_dispatcher import (
    WebhookDispatcher,
    WebhookEvent,
)


@dataclass
class FakeResponse:
    """Konkreten ``DeliveryResponse`` za fake driver."""

    ok: bool = False
    status_code: int = 0
    permanent: bool = False
    error: str = ""


class FakeDriver:
    """Transportna vstavitvena točka: vrača vnaprej pripravljene odzive."""

    def __init__(self, responses: Optional[List[Any]] = None):
        self.responses: List[Any] = list(responses or [])
        self.calls: List[Dict[str, Any]] = []  # zajemi (url, headers, payload)

    async def send(self, url: str, headers: Dict[str, str], payload: bytes) -> Any:
        self.calls.append({"url": url, "headers": headers, "payload": payload})
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse(ok=True, status_code=200)


class FakeSleeper:
    """Nadomestni backoff spanje: samo beleži zamike, ne spi."""

    def __init__(self):
        self.delays: List[float] = []

    async def __call__(self, delay: float):
        self.delays.append(delay)


@pytest.fixture(autouse=True)
def _fresh_dispatcher():
    """Vsak test svež dispatcher (ne kontaminira drugih testov / app stanja)."""
    dispatcher.subscribers.clear()
    dispatcher.dead_letter.clear()
    dispatcher._delivered.clear()
    yield


# ── HMAC podpis ─────────────────────────────────────────────────────────────
def test_sign_and_verify_signature():
    sig = WebhookDispatcher.sign_payload("secret123", b'{"a":1}')
    assert sig.startswith("sha256=")
    assert WebhookDispatcher.verify_signature("secret123", b'{"a":1}', sig) is True
    # Napačen payload/secret → ne verificira.
    assert WebhookDispatcher.verify_signature("secret123", b'{"a":2}', sig) is False
    assert WebhookDispatcher.verify_signature("drug1234", b'{"a":1}', sig) is False


# ── Registracija ────────────────────────────────────────────────────────────
def test_register_unregister_list():
    d = WebhookDispatcher(driver=FakeDriver())
    sub = d.register_subscriber("https://example.com/hook", "secret123", events=["invoice.paid"])
    assert sub.id in d.subscribers
    assert d.unregister_subscriber(sub.id) is True
    assert d.unregister_subscriber(sub.id) is False
    assert d.subscribers == {}


def test_subscribed_matching():
    d = WebhookDispatcher(driver=FakeDriver())
    wildcard = d.register_subscriber("https://a.example/h", "secret123", events=["*"])
    specific = d.register_subscriber("https://b.example/h", "secret123", events=["invoice.paid"])
    assert d._subscribed(wildcard, "anything") is True
    assert d._subscribed(specific, "invoice.paid") is True
    assert d._subscribed(specific, "order.created") is False


# ── Dostava + retry + DLQ ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_delivery_ok_single_attempt():
    driver = FakeDriver([FakeResponse(ok=True, status_code=200)])
    sleeper = FakeSleeper()
    d = WebhookDispatcher(driver=driver, sleeper=sleeper)
    sub = d.register_subscriber("https://example.com/hook", "secret123", events=["*"])
    event = WebhookEvent(type="invoice.paid", payload={"amount": 10})
    results = await d.dispatch_event(event)

    assert len(results) == 1
    assert results[0].status == "delivered"
    assert results[0].attempts == 1
    assert len(driver.calls) == 1
    # Idempotency ključ je v headerjih.
    assert driver.calls[0]["headers"]["X-Idempotency-Key"] == event.event_id
    # Podpis je prisoten in verifiable.
    sig = driver.calls[0]["headers"]["X-RobAI-Signature"]
    assert WebhookDispatcher.verify_signature("secret123", driver.calls[0]["payload"], sig)


@pytest.mark.asyncio
async def test_retry_exponential_backoff_then_success():
    # 2× transientno (network), 3. poskus OK.
    driver = FakeDriver(
        [
            FakeResponse(ok=False, status_code=0, permanent=False, error="conn refused"),
            FakeResponse(ok=False, status_code=502, permanent=False, error="HTTP 502"),
            FakeResponse(ok=True, status_code=200),
        ]
    )
    sleeper = FakeSleeper()
    d = WebhookDispatcher(driver=driver, sleeper=sleeper)
    d.register_subscriber("https://example.com/hook", "secret123", max_attempts=3, base_delay_seconds=1.0)
    results = await d.dispatch_event(WebhookEvent(type="t", payload={}))

    assert results[0].status == "delivered"
    assert results[0].attempts == 3
    assert sleeper.delays == [1.0, 2.0]  # eksponentni backoff: d, 2d


@pytest.mark.asyncio
async def test_permanent_failure_goes_straight_to_dlq():
    driver = FakeDriver([FakeResponse(ok=False, status_code=404, permanent=True, error="HTTP 404")])
    sleeper = FakeSleeper()
    d = WebhookDispatcher(driver=driver, sleeper=sleeper)
    sub = d.register_subscriber("https://example.com/hook", "secret123")
    await d.dispatch_event(WebhookEvent(type="t", payload={}))

    assert len(d.dead_letter) == 1
    assert d.dead_letter[0]["subscriber_id"] == sub.id
    # Mrtvi subscriber se samodejno deaktivira.
    assert sub.active is False
    assert sleeper.delays == []  # brez backoffa pri permanentni napaki


@pytest.mark.asyncio
async def test_retries_exhausted_goes_to_dlq():
    driver = FakeDriver(
        [
            FakeResponse(ok=False, status_code=500, permanent=False, error="HTTP 500"),
            FakeResponse(ok=False, status_code=500, permanent=False, error="HTTP 500"),
        ]
    )
    sleeper = FakeSleeper()
    d = WebhookDispatcher(driver=driver, sleeper=sleeper)
    d.register_subscriber("https://example.com/hook", "secret123", max_attempts=2)
    results = await d.dispatch_event(WebhookEvent(type="t", payload={}))

    assert results[0].status == "dead"
    assert len(d.dead_letter) == 1


@pytest.mark.asyncio
async def test_idempotency_skips_second_dispatch():
    driver = FakeDriver([FakeResponse(ok=True, status_code=200)])
    sleeper = FakeSleeper()
    d = WebhookDispatcher(driver=driver, sleeper=sleeper)
    d.register_subscriber("https://example.com/hook", "secret123")
    event = WebhookEvent(type="t", payload={"x": 1})

    r1 = await d.dispatch_event(event)
    r2 = await d.dispatch_event(event)

    assert r1[0].status == "delivered"
    assert r2[0].status == "skipped"
    assert r2[0].error == "idempotent"
    assert len(driver.calls) == 1  # samo ena realna dostava


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_register_and_health():
    client = TestClient(app)
    r = client.post("/subscribers", json={"url": "https://x.example/h", "secret": "secret123", "events": ["*"]})
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert "secret" not in body  # nikoli ne razkrijemo secret-a

    h = client.get("/health")
    assert h.status_code == 200
    assert h.json()["subscribers"] >= 1


def test_api_rejects_non_http_url():
    client = TestClient(app)
    r = client.post("/subscribers", json={"url": "file:///etc/passwd", "secret": "secret123"})
    assert r.status_code == 422
