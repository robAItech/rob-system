"""
Enterprise Core Contracts - Schemas (združeni v API Gateway).

Definira jedrne Pydantic modele (DTO), interfase in enume, ki se uporabljajo
povsod po sistemu. To je stroga podatkovna plast BREZ poslovne logike.

Izvor: nekdanji samostojni modul ``core_contracts.schemas``.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

from pydantic import BaseModel, Field, field_validator

# Type variable for generic models
T = TypeVar("T")


class StatusEnum(str, Enum):
    """System-wide status enum."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    DELETED = "deleted"
    ERROR = "error"
    SUCCESS = "success"


class EventTypeEnum(str, Enum):
    """System-wide event type enum."""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    READ = "read"
    ERROR = "error"
    VALIDATION = "validation"


class BaseEvent(BaseModel):
    """
    Base event model for all system events.

    Attributes:
        event_id: Unique identifier for the event
        event_type: Type of the event
        timestamp: When the event occurred
        source: Source system/module that generated the event
        payload: Event payload data
    """
    event_id: str = Field(..., min_length=1, max_length=100)
    event_type: EventTypeEnum
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field(..., min_length=1, max_length=200)
    payload: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        """Validate event_id is not empty."""
        if not v.strip():
            raise ValueError("event_id cannot be empty")
        return v.strip()

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        """Validate source is not empty."""
        if not v.strip():
            raise ValueError("source cannot be empty")
        return v.strip()


class ErrorResponse(BaseModel):
    """
    Standard error response model.

    Attributes:
        status: Status of the response (always 'error')
        error_code: Machine-readable error code
        message: Human-readable error message
        details: Additional error details
        timestamp: When the error occurred
    """
    status: StatusEnum = StatusEnum.ERROR
    error_code: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=1000)
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("error_code")
    @classmethod
    def validate_error_code(cls, v: str) -> str:
        """Validate error_code is not empty."""
        if not v.strip():
            raise ValueError("error_code cannot be empty")
        return v.strip()

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message is not empty."""
        if not v.strip():
            raise ValueError("message cannot be empty")
        return v.strip()


class SuccessResponse(BaseModel):
    """
    Standard success response model.

    Attributes:
        status: Status of the response (always 'success')
        data: Response data
        message: Optional success message
        timestamp: When the response was generated
    """
    status: StatusEnum = StatusEnum.SUCCESS
    data: Any = None
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ValidationErrorResponse(BaseModel):
    """
    Validation error response model.

    Attributes:
        status: Status of the response (always 'error')
        error_code: Machine-readable error code (always 'VALIDATION_ERROR')
        message: Human-readable error message
        errors: List of validation errors
        timestamp: When the error occurred
    """
    status: StatusEnum = StatusEnum.ERROR
    error_code: str = "VALIDATION_ERROR"
    message: str = "Validation failed"
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaginationParams(BaseModel):
    """
    Pagination parameters model.

    Attributes:
        page: Page number (1-indexed)
        page_size: Number of items per page
        sort_by: Field to sort by
        sort_order: Sort order ('asc' or 'desc')
    """
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field(default=None, max_length=100)
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated response model.

    Attributes:
        items: List of items
        total: Total number of items
        page: Current page number
        page_size: Number of items per page
        total_pages: Total number of pages
    """
    items: List[T]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=0)

    @field_validator("total_pages")
    @classmethod
    def validate_total_pages(cls, v: int, info) -> int:
        """Validate total_pages is consistent with total and page_size."""
        total = info.data.get("total", 0)
        page_size = info.data.get("page_size", 1)
        expected = (total + page_size - 1) // page_size if page_size > 0 else 0
        if v != expected:
            raise ValueError(f"total_pages must be {expected}")
        return v


class BaseEntity(BaseModel):
    """
    Base entity model for all system entities.

    Attributes:
        id: Unique identifier
        created_at: When the entity was created
        updated_at: When the entity was last updated
        status: Current status of the entity
    """
    id: str = Field(..., min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: StatusEnum = StatusEnum.ACTIVE

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        """Validate id is not empty."""
        if not v.strip():
            raise ValueError("id cannot be empty")
        return v.strip()


class HealthResponse(BaseModel):
    """
    Health check response model.

    Attributes:
        status: Service status
        version: Service version
        timestamp: When the health check was performed
    """
    status: str = "ok"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
