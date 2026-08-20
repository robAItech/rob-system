"""
Enterprise Core — unified data contracts + utility functions.

Združitev nekdanjih ``core_contracts_contracts`` (DTO-ji, enumi, helper funkcije)
in ``core_contracts_utils`` (TimestampNormalizer, HashUtils) v en jedrni modul.
"""

from actions.core_contracts.schemas import (
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
from actions.core_contracts.contracts import (
    create_error_response,
    create_health_response,
    create_success_response,
    create_validation_error_response,
    validate_event,
)
from actions.core_contracts.utils import HashUtils, TimestampNormalizer

__all__ = [
    # schemas
    "BaseEntity", "BaseEvent", "ErrorResponse", "EventTypeEnum", "HealthResponse",
    "PaginatedResponse", "PaginationParams", "StatusEnum", "SuccessResponse",
    "ValidationErrorResponse",
    # contracts helper funkcije
    "create_error_response", "create_health_response", "create_success_response",
    "create_validation_error_response", "validate_event",
    # utility razredi
    "HashUtils", "TimestampNormalizer",
]

__version__ = "1.0.0"
