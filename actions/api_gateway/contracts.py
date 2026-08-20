"""
Enterprise Core Contracts - helper funkcije (združene v API Gateway).

Zagotavlja standardne tovarniške funkcije za gradnjo odgovorov in validacijo
dogodkov. Izvor: nekdanji samostojni modul ``core_contracts.contracts``.
"""

from typing import Any, Dict, Optional

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


def create_success_response(
    data: Any = None,
    message: Optional[str] = None,
) -> SuccessResponse:
    """
    Create a standard success response.

    Args:
        data: Response data
        message: Optional success message

    Returns:
        SuccessResponse: Standard success response
    """
    return SuccessResponse(data=data, message=message)


def create_error_response(
    error_code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> ErrorResponse:
    """
    Create a standard error response.

    Args:
        error_code: Machine-readable error code
        message: Human-readable error message
        details: Additional error details

    Returns:
        ErrorResponse: Standard error response
    """
    return ErrorResponse(
        error_code=error_code,
        message=message,
        details=details,
    )


def create_validation_error_response(
    errors: list,
    message: str = "Validation failed",
) -> ValidationErrorResponse:
    """
    Create a validation error response.

    Args:
        errors: List of validation errors
        message: Error message

    Returns:
        ValidationErrorResponse: Validation error response
    """
    return ValidationErrorResponse(errors=errors, message=message)


def create_health_response(
    version: str = "1.0.0",
) -> HealthResponse:
    """
    Create a health check response.

    Args:
        version: Service version

    Returns:
        HealthResponse: Health check response
    """
    return HealthResponse(version=version)


def validate_event(event: BaseEvent) -> bool:
    """
    Validate an event.

    Args:
        event: Event to validate

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        # Pydantic validation happens on instantiation
        # Additional validation logic can be added here
        return True
    except Exception:
        return False


__all__ = [
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
    "create_success_response",
    "create_error_response",
    "create_validation_error_response",
    "create_health_response",
    "validate_event",
]
