"""webhook_dispatcher — jedro domenske logike: zanesljiva B2B dostava dogodkov.

Kot predlaga arhitekturna revizija (3.1): robustna asinhrona dostava dogodkov do
zunanjih sistemov z:
  - HMAC-SHA256 podpisom payloada in verifikacijo na cilju,
  - idempotency ključem (deduplikacija dostav),
  - retry z eksponentnim backoffom (integracijska točka: ``retry_wrapper``),
  - dead-letter queue (DLQ) za neponovljive napake,
  - health-checkom ciljnih endpointov in deaktivacijo mrtvih subscriberjev.

Transport je vstavitvena točka (``DeliveryDriver``) — v testih fake driver, v
produkciji ``HttpDeliveryDriver`` (httpx). Vse stanje je v spominu (mono-repo
testno okolje); brez omrežja ob uvozu.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

DEFAULT_SLEEPER: Callable[[float], Any] = asyncio.sleep


class DeliveryResponse(Protocol):
    """Rezultat enega transportnega poskusa (protokol za fake/test drivere)."""

    ok: bool
    status_code: int
    permanent: bool
    error: str


@dataclass
class HttpDeliveryResult:
    """Konkreten ``DeliveryResponse`` — iz http poskusa ali fika v testih."""

    ok: bool = False
    status_code: int = 0
    permanent: bool = False
    error: str = ""


class DeliveryDriver(Protocol):
    """Abstrakcija HTTP transporta (vstavitvena točka za testiranje)."""

    async def send(self, url: str, headers: Dict[str, str], payload: bytes) -> DeliveryResponse: ...


class HttpDeliveryDriver:
    """Realni transport: ``httpx.AsyncClient`` z timeoutom (brez redirect sledenja)."""

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds

    async def send(self, url: str, headers: Dict[str, str], payload: bytes) -> HttpDeliveryResult:
        import httpx  # lazily — omrežni klient ne sme biti ob uvozu modula

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
                resp = await client.post(url, headers=headers, content=payload)
        except Exception as exc:  # omrežna napaka → transientno, retry
            return HttpDeliveryResult(ok=False, status_code=0, permanent=False, error=str(exc))
        permanent = 400 <= resp.status_code < 500
        return HttpDeliveryResult(
            ok=resp.status_code < 400,
            status_code=resp.status_code,
            permanent=permanent,
            error="" if resp.status_code < 400 else f"HTTP {resp.status_code}",
        )


@dataclass
class WebhookSubscriber:
    """Naročnik na dogodke: URL, secret, politika dostave."""

    id: str
    url: str
    secret: str
    events: List[str]
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    active: bool = True
    created_at: float = 0.0


@dataclass
class DeliveryResult:
    """Izid dostave enega dogodka enemu subscriberju."""

    event_id: str
    subscriber_id: str
    status: str  # delivered | retrying | dead | skipped
    attempts: int = 0
    error: str = ""


@dataclass
class WebhookEvent:
    """Dogodek za dostavo (idempotency ključ = event_id)."""

    type: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class WebhookDispatcher:
    """Registracija subscriberjev + dostava dogodkov z retry/DLQ/health."""

    def __init__(
        self,
        driver: Optional[DeliveryDriver] = None,
        sleeper: Optional[Callable[[float], Any]] = None,
    ):
        self.driver: DeliveryDriver = driver or HttpDeliveryDriver()
        self._sleeper = sleeper or DEFAULT_SLEEPER
        self.subscribers: Dict[str, WebhookSubscriber] = {}
        self.dead_letter: List[Dict[str, Any]] = []
        # Idempotency: (subscriber_id, event_id) → True, če je že dostavljeno.
        self._delivered: set = set()

    # ── Registracija ────────────────────────────────────────────────────────
    def register_subscriber(
        self,
        url: str,
        secret: str,
        events: Optional[List[str]] = None,
        max_attempts: int = 3,
        base_delay_seconds: float = 0.5,
        active: bool = True,
    ) -> WebhookSubscriber:
        """Registriraj novega subscriberja; vrne ga z unikatnim id-jem."""
        sub = WebhookSubscriber(
            id=uuid.uuid4().hex[:12],
            url=url,
            secret=secret,
            events=list(events or ["*"]),
            max_attempts=max_attempts,
            base_delay_seconds=base_delay_seconds,
            active=active,
        )
        self.subscribers[sub.id] = sub
        return sub

    def unregister_subscriber(self, subscriber_id: str) -> bool:
        """Odstrani subscriberja; False, če ne obstaja."""
        if subscriber_id not in self.subscribers:
            return False
        del self.subscribers[subscriber_id]
        return True

    def set_active(self, subscriber_id: str, active: bool) -> bool:
        """Deaktiviraj/aktiviraj subscriberja (health-check / admin)."""
        sub = self.subscribers.get(subscriber_id)
        if sub is None:
            return False
        sub.active = active
        return True

    def _subscribed(self, sub: WebhookSubscriber, event_type: str) -> bool:
        """Ali je subscriber naročen na tip dogodka? (``*`` = vse)."""
        return "*" in sub.events or event_type in sub.events

    # ── Podpis ──────────────────────────────────────────────────────────────
    @staticmethod
    def sign_payload(secret: str, payload: bytes) -> str:
        """HMAC-SHA256 podpis payloada (hex). Verifikacija: hmac.compare_digest."""
        digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    @staticmethod
    def verify_signature(secret: str, payload: bytes, signature: str) -> bool:
        """Preveri podpis ob prejemu (konstantnočasovna primerjava)."""
        expected = WebhookDispatcher.sign_payload(secret, payload)
        return hmac.compare_digest(expected, signature)

    # ── Dostava ─────────────────────────────────────────────────────────────
    def _delivered_key(self, sub_id: str, event_id: str) -> str:
        return f"{sub_id}:{event_id}"

    def _build_headers(self, sub: WebhookSubscriber, event: WebhookEvent, payload: bytes) -> Dict[str, str]:
        """Idempotency ključ + podpis + metapodatki dogodka."""
        return {
            "Content-Type": "application/json",
            "X-RobAI-Event-Type": event.type,
            "X-Idempotency-Key": event.event_id,
            "X-RobAI-Signature": self.sign_payload(sub.secret, payload),
        }

    async def _deliver_once(self, sub: WebhookSubscriber, event: WebhookEvent, payload: bytes) -> DeliveryResponse:
        """Eden transportni poskus (driver call)."""
        headers = self._build_headers(sub, event, payload)
        return await self.driver.send(sub.url, headers, payload)

    async def _deliver_with_retry(self, sub: WebhookSubscriber, event: WebhookEvent) -> DeliveryResult:
        """Eksponentni backoff: 4xx → DLQ takoj; 5xx/omrežje → retry do max_attempts."""
        payload = json.dumps(event.payload, ensure_ascii=False).encode("utf-8")
        delay = sub.base_delay_seconds
        for attempt in range(1, sub.max_attempts + 1):
            resp = await self._deliver_once(sub, event, payload)
            if resp.ok:
                return DeliveryResult(event.event_id, sub.id, "delivered", attempts=attempt)
            if resp.permanent:
                # Neponovljiva napaka → direktno DLQ.
                return DeliveryResult(event.event_id, sub.id, "dead", attempts=attempt, error=resp.error)
            if attempt < sub.max_attempts:
                await self._sleeper(delay)
                delay *= 2  # eksponentni backoff: d, 2d, 4d, ...
        return DeliveryResult(event.event_id, sub.id, "dead", attempts=sub.max_attempts, error="retries exhausted")

    async def dispatch_event(self, event: WebhookEvent) -> List[DeliveryResult]:
        """Dostavi dogodek vsem naročenim aktivnim subscriberjem.

        Idempotentno: že dostavljen (subscriber_id, event_id) se preskoči.
        """
        results: List[DeliveryResult] = []
        for sub in list(self.subscribers.values()):
            if not sub.active or not self._subscribed(sub, event.type):
                continue
            key = self._delivered_key(sub.id, event.event_id)
            if key in self._delivered:
                results.append(DeliveryResult(event.event_id, sub.id, "skipped", attempts=0, error="idempotent"))
                continue
            result = await self._deliver_with_retry(sub, event)
            if result.status == "delivered":
                self._delivered.add(key)
            elif result.status == "dead":
                self.dead_letter.append(
                    {
                        "event_id": event.event_id,
                        "subscriber_id": sub.id,
                        "url": sub.url,
                        "status": result.status,
                        "attempts": result.attempts,
                        "error": result.error,
                    }
                )
                # Mrtvi subscriber se samodejno deaktivira (health).
                self.set_active(sub.id, False)
            results.append(result)
        return results

    # ── Health ──────────────────────────────────────────────────────────────
    async def health_check(self) -> Dict[str, Any]:
        """Pregled: število subscriberjev, mrtvih, DLQ, deaktiviranih."""
        return {
            "status": "UP",
            "subscribers": len(self.subscribers),
            "active": sum(1 for s in self.subscribers.values() if s.active),
            "inactive": sum(1 for s in self.subscribers.values() if not s.active),
            "dead_letter": len(self.dead_letter),
        }
