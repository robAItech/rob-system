"""Pytest test suite za actions/telemetry_bus (Refaktor 2).

Preveri: korelacijske ID-je, sink razpošiljanje, transport prek event_bus-a,
audit kot sink (AuditEventSink) in FastAPI plast. Brez omrežja.
"""

import asyncio
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from actions.telemetry_bus.main import app, bus
from actions.telemetry_bus.telemetry import (
    AuditEventSink,
    TelemetryBus,
    TelemetryEvent,
)


@pytest.fixture(autouse=True)
def _fresh_bus():
    bus.events.clear()
    bus._sinks.clear()
    yield


# ── Korelacijski ID ─────────────────────────────────────────────────────────
async def test_publish_generates_correlation_id():
    tb = TelemetryBus()
    e = await tb.publish("order.created", {"order": 1})
    assert e.correlation_id
    assert len(e.correlation_id) == 16


async def test_publish_propagates_payload_correlation_id():
    tb = TelemetryBus()
    e = await tb.publish("order.created", {"correlation_id": "abc123", "order": 1})
    assert e.correlation_id == "abc123"


async def test_publish_explicit_correlation_id_wins():
    tb = TelemetryBus()
    e = await tb.publish("order.created", {"correlation_id": "from_payload"}, "explicit")
    assert e.correlation_id == "explicit"


# ── Sink-i ──────────────────────────────────────────────────────────────────
async def test_subscribe_receives_events():
    tb = TelemetryBus()
    seen: List[TelemetryEvent] = []

    def sink(ev: TelemetryEvent):
        seen.append(ev)

    tb.subscribe(sink)
    await tb.publish("a", {"x": 1})
    assert len(seen) == 1
    assert seen[0].type == "a"

    tb.unsubscribe(sink)
    await tb.publish("b", {})
    assert len(seen) == 1  # po unsubscribe ne dobiva več


async def test_publish_forwards_to_event_bus_transport():
    from actions.event_bus.event_bus import EventBus

    eb = EventBus()
    tb = TelemetryBus(event_bus=eb)
    await tb.publish("invoice.paid", {"amount": 10})
    msgs = eb.get_topic_messages("invoice.paid")
    assert len(msgs) == 1
    assert msgs[0]["payload"] == {"amount": 10}


# ── Audit kot sink ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_audit_event_sink_writes_to_audit_trail():
    from actions.audit_trail.audit_trail import AuditTrail

    trail = AuditTrail()
    tb = TelemetryBus()
    sink = AuditEventSink(trail)
    tb.subscribe(sink)

    await tb.publish("user.login", {"actor": "admin", "action": "LOGIN", "target": "sys"})
    assert len(trail.chain) == 1
    assert trail.chain[0].actor == "admin"
    assert trail.chain[0].action == "LOGIN"
    # correlation_id se prenese v payload zapisa.
    assert "correlation_id" in trail.chain[0].payload


# ── Observability ───────────────────────────────────────────────────────────
async def test_stats_by_type():
    tb = TelemetryBus()
    await tb.publish("a", {})
    await tb.publish("a", {})
    await tb.publish("b", {})
    assert tb.stats() == {"total": 3, "by_type": {"a": 2, "b": 1}}


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_publish_events_stats_health():
    client = TestClient(app)
    r = client.post("/publish", json={"type": "invoice.paid", "payload": {"amount": 5}})
    assert r.status_code == 200
    body = r.json()
    assert body["correlation_id"]

    evs = client.get("/events").json()
    assert len(evs) == 1 and evs[0]["type"] == "invoice.paid"

    stats = client.get("/stats").json()
    assert stats["total"] == 1

    assert client.get("/health").json()["status"] == "UP"
