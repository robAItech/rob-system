"""
Enterprise Core Contracts module.

This module provides the foundational data contracts (DTOs), interfaces, and enums
used across the entire system. It is a strict data layer with NO business logic.
"""

from actions.enterprise_core_contracts.schemas import (
    BaseEvent,
    ErrorResponse,
    StatusEnum,
    EventTypeEnum,
    PaginationParams,
    PaginatedResponse,
    SuccessResponse,
    ValidationErrorResponse,
)

__all__ = [
    "BaseEvent",
    "ErrorResponse",
    "StatusEnum",
    "EventTypeEnum",
    "PaginationParams",
    "PaginatedResponse",
    "SuccessResponse",
    "ValidationErrorResponse",
]

__version__ = "1.0.0"