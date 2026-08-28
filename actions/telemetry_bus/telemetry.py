"""telemetry_bus — konsolidiran korelacijski dogodkovni vod (Refaktor 2).

Arhitekturna revizija (2026): `audit_trail`, `observability_metrics` in
`event_bus` se poenotijo v EN interni kanal. ``TelemetryBus``:
  - razpošilja dogodke s **korelacijskim ID-jem** (sledljivost čez celotno verigo),
  - uporablja obstoječi ``event_bus`` kot transport (javni API ostane),
  - sink-i (npr. audit, metrike) se naročijo na kanal — audit postane sink,
  - hrani zgodovino dogodkov za observability.

Vse je čisto in deterministično (brez omrežja); ``correlation_id`` se
generira ali prenese iz payloada.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

#: Vrsta sink-a: callable, ki sprejme TelemetryEvent in ne vrne nič.
TelemetrySink = Callable[["TelemetryEvent"], Any]


@dataclass
class TelemetryEvent:
    """Eden dogodek na korelacijskem vodilu."""

    type: str
    payload: Dict[str, Any]
    correlation_id: str
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    timestamp: float = field(default_factory=time.time)


class TelemetryBus:
    """Enotni dogodkovni vod s korelacijskimi ID-ji in sink-i.

    Args:
        event_bus: opcijski obstoječi ``EventBus`` (actions.event_bus) — uporabi
            se kot transport: vsak objavljen dogodek gre tudi nanj (topic = type).
    """

    def __init__(self, event_bus: Optional[Any] = None):
        self.event_bus = event_bus
        self._sinks: List[TelemetrySink] = []
        self.events: List[TelemetryEvent] = []

    # ── Korelacija ───────────────────────────────────────────────────────────
    @staticmethod
    def new_correlation_id() -> str:
        return uuid.uuid4().hex[:16]

    def _extract_correlation_id(self, payload: Dict[str, Any]) -> str:
        """Vzemi ``correlation_id`` iz payloada ali generiraj novega."""
        cid = payload.get("correlation_id") if isinstance(payload, dict) else None
        return str(cid) if cid else self.new_correlation_id()

    # ── Sink-i ───────────────────────────────────────────────────────────────
    def subscribe(self, sink: TelemetrySink) -> TelemetrySink:
        """Registriraj sink (audit, metrike, ...); vrne ga za convenience."""
        if sink not in self._sinks:
            self._sinks.append(sink)
        return sink

    def unsubscribe(self, sink: TelemetrySink) -> bool:
        if sink in self._sinks:
            self._sinks.remove(sink)
            return True
        return False

    # ── Objava ──────────────────────────────────────────────────────────────
    async def publish(
        self,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> TelemetryEvent:
        """Objavi dogodek: pokliči vse sink-e (sync/async) + transport.

        Async sink-i (npr. AuditEventSink, ki piše v AuditTrail) se await-ajo.
        """
        import asyncio

        payload = dict(payload or {})
        cid = correlation_id or self._extract_correlation_id(payload)
        event = TelemetryEvent(
            type=event_type, payload=payload, correlation_id=cid
        )
        self.events.append(event)
        for sink in list(self._sinks):
            result = sink(event)
            if asyncio.iscoroutine(result):
                await result
        if self.event_bus is not None:
            self.event_bus.publish(event.type, event.payload)
        return event

    # ── Observability ───────────────────────────────────────────────────────
    def events_by_type(self, event_type: str) -> List[TelemetryEvent]:
        return [e for e in self.events if e.type == event_type]

    def stats(self) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        for e in self.events:
            by_type[e.type] = by_type.get(e.type, 0) + 1
        return {"total": len(self.events), "by_type": by_type}


# ── Sink adapter: audit (audit_trail postane sink na vodilu) ────────────────
class AuditEventSink:
    """Adapter, ki audit-record (dict) zapiše v dani recorder (AuditTrail).

    Sink prejme ``TelemetryEvent``; iz njega zgradi audit zapis (actor/target/
    action iz payloada s privzetimi vrednostmi).
    """

    def __init__(self, audit_trail: Any):
        self.audit_trail = audit_trail

    async def __call__(self, event: TelemetryEvent) -> None:
        payload = dict(event.payload)
        from actions.audit_trail.schemas import AuditRecordCreate

        await self.audit_trail.record_event(
            AuditRecordCreate(
                actor=payload.pop("actor", "system"),
                action=payload.pop("action", event.type),
                target=payload.pop("target", event.type),
                payload={**payload, "correlation_id": event.correlation_id},
            )
        )


__all__ = [
    "TelemetryEvent",
    "TelemetryBus",
    "TelemetrySink",
    "AuditEventSink",
]
