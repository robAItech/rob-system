"""webhook_dispatcher — zanesljiva B2B dostava eventov (enterprise webhook).

Javni API:
    WebhookDispatcher(driver, sleeper) → register/dispatch/dead_letter/health
    sign_payload(secret, payload) → HMAC-SHA256 podpis
    verify_signature(secret, payload, signature) → konstantnočasovna verifikacija
"""

from actions.webhook_dispatcher.webhook_dispatcher import (
    WebhookDispatcher,
    WebhookEvent,
    WebhookSubscriber,
    DeliveryResult,
    HttpDeliveryDriver,
)

# Convenience: module-level helpera (delegata na statične metode razreda).
sign_payload = WebhookDispatcher.sign_payload
verify_signature = WebhookDispatcher.verify_signature

__all__ = [
    "WebhookDispatcher",
    "WebhookEvent",
    "WebhookSubscriber",
    "DeliveryResult",
    "HttpDeliveryDriver",
    "sign_payload",
    "verify_signature",
]
