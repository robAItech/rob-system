"""
Enterprise API Gateway — unified gateway (routing + webhooks).

Združitev nekdanjih ``enterprise_unified_gateway`` (GatewayRouter) in
``enterprise_webhook_dispatcher`` (EnterpriseWebhookDispatcher) v en vhodni point.
"""

from actions.api_gateway.gateway import GatewayRouter
from actions.api_gateway.webhooks import EnterpriseWebhookDispatcher
from actions.api_gateway.schemas import (
    RoutePayload,
    RouteResponse,
    WebhookStatus,
    WebhookEndpoint,
    WebhookEvent,
    DeliveryAttempt,
    DeliveryResult,
)

__all__ = [
    "GatewayRouter",
    "EnterpriseWebhookDispatcher",
    "RoutePayload",
    "RouteResponse",
    "WebhookStatus",
    "WebhookEndpoint",
    "WebhookEvent",
    "DeliveryAttempt",
    "DeliveryResult",
]

__version__ = "1.0.0"
