"""
Enterprise API Gateway — unified gateway (routing + webhooks + versioning + contracts).

Združitev nekdanjih samostojnih modulov v en vhodni point:
- ``gateway``  — GatewayRouter (usmerjanje)
- ``webhooks`` — WebhookDispatcher (razpošiljanje)
- ``versioning`` — VersionManager + VersionValidationMiddleware (združeni api_versioning)
- ``core_schemas``/``contracts``/``utils`` — jedrni DTO-ji, helper funkcije in utility (združeni core_contracts)
"""

from actions.api_gateway.gateway import GatewayRouter
from actions.api_gateway.webhooks import WebhookDispatcher
from actions.api_gateway.versioning import VersionManager, VersionValidationMiddleware
from actions.api_gateway.schemas import (
    RoutePayload,
    RouteResponse,
    WebhookStatus,
    WebhookEndpoint,
    WebhookEvent,
    DeliveryAttempt,
    DeliveryResult,
)
from actions.api_gateway.core_schemas import (
    BaseEntity,
    BaseEvent,
    ErrorResponse,
    EventTypeEnum,
    HealthResponse,
    PaginatedResponse,
    PaginationParams,
    StatusEnum,
    SuccessResponse,
    ValidationErrorResponse,
)
from actions.api_gateway.contracts import (
    create_success_response,
    create_error_response,
    create_validation_error_response,
    create_health_response,
    validate_event,
)
from actions.api_gateway.utils import HashUtils, TimestampNormalizer

__all__ = [
    "GatewayRouter",
    "WebhookDispatcher",
    "VersionManager",
    "VersionValidationMiddleware",
    "RoutePayload",
    "RouteResponse",
    "WebhookStatus",
    "WebhookEndpoint",
    "WebhookEvent",
    "DeliveryAttempt",
    "DeliveryResult",
    # core_contracts DTO-ji
    "BaseEntity",
    "BaseEvent",
    "ErrorResponse",
    "EventTypeEnum",
    "HealthResponse",
    "PaginatedResponse",
    "PaginationParams",
    "StatusEnum",
    "SuccessResponse",
    "ValidationErrorResponse",
    # contracts helper funkcije
    "create_success_response",
    "create_error_response",
    "create_validation_error_response",
    "create_health_response",
    "validate_event",
    # utility razredi
    "HashUtils",
    "TimestampNormalizer",
]

__version__ = "1.0.0"
