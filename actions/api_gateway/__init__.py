"""
Enterprise API Gateway — unified gateway (routing + webhooks).

Združitev gatewaya (GatewayRouter) in webhookov (WebhookDispatcher) v en vhodni point.
"""

from actions.api_gateway.gateway import GatewayRouter
from actions.api_gateway.webhooks import WebhookDispatcher
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
    "WebhookDispatcher",
    "RoutePayload",
    "RouteResponse",
    "WebhookStatus",
    "WebhookEndpoint",
    "WebhookEvent",
    "DeliveryAttempt",
    "DeliveryResult",
]

__version__ = "1.0.0"
