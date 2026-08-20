"""
Enterprise Core Contracts - Tests.

This module contains comprehensive tests for all schemas and models.
"""

import pytest
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi.testclient import TestClient
from pydantic import ValidationError

from actions.enterprise_core.main import app
from actions.enterprise_core.schemas import (
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
from actions.enterprise_core.contracts import (
    create_success_response,
    create_error_response,
    create_validation_error_response,
    create_health_response,
    validate_event,
)


# Test client fixture
@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


# =============================================================================
# StatusEnum Tests
# =============================================================================

class TestStatusEnum:
    """Test StatusEnum."""

    def test_status_values(self):
        """Test all status values."""
        assert StatusEnum.ACTIVE.value == "active"
        assert StatusEnum.INACTIVE.value == "inactive"
        assert StatusEnum.PENDING.value == "pending"
        assert StatusEnum.DELETED.value == "deleted"
        assert StatusEnum.ERROR.value == "error"
        assert StatusEnum.SUCCESS.value == "success"

    def test_status_members(self):
        """Test all status members exist."""
        expected = {"ACTIVE", "INACTIVE", "PENDING", "DELETED", "ERROR", "SUCCESS"}
        assert set(StatusEnum.__members__.keys()) == expected


# =============================================================================
# EventTypeEnum Tests
# =============================================================================

class TestEventTypeEnum:
    """Test EventTypeEnum."""

    def test_event_type_values(self):
        """Test all event type values."""
        assert EventTypeEnum.CREATED.value == "created"
        assert EventTypeEnum.UPDATED.value == "updated"
        assert EventTypeEnum.DELETED.value == "deleted"
        assert EventTypeEnum.READ.value == "read"
        assert EventTypeEnum.ERROR.value == "error"
        assert EventTypeEnum.VALIDATION.value == "validation"

    def test_event_type_members(self):
        """Test all event type members exist."""
        expected = {"CREATED", "UPDATED", "DELETED", "READ", "ERROR", "VALIDATION"}
        assert set(EventTypeEnum.__members__.keys()) == expected


# =============================================================================
# BaseEvent Tests
# =============================================================================

class TestBaseEvent:
    """Test BaseEvent model."""

    def test_valid_event(self):
        """Test creating a valid event."""
        event = BaseEvent(
            event_id="evt_001",
            event_type=EventTypeEnum.CREATED,
            source="test_module",
            payload={"key": "value"},
        )
        assert event.event_id == "evt_001"
        assert event.event_type == EventTypeEnum.CREATED
        assert event.source == "test_module"
        assert event.payload == {"key": "value"}
        assert isinstance(event.timestamp, datetime)

    def test_event_default_payload(self):
        """Test event with default payload."""
        event = BaseEvent(
            event_id="evt_002",
            event_type=EventTypeEnum.READ,
            source="test_module",
        )
        assert event.payload == {}

    def test_event_empty_event_id(self):
        """Test event with empty event_id."""
        with pytest.raises(ValidationError):
            BaseEvent(
                event_id="",
                event_type=EventTypeEnum.CREATED,
                source="test_module",
            )

    def test_event_whitespace_event_id(self):
        """Test event with whitespace event_id."""
        with pytest.raises(ValidationError):
            BaseEvent(
                event_id="   ",
                event_type=EventTypeEnum.CREATED,
                source="test_module",
            )

    def test_event_empty_source(self):
        """Test event with empty source."""
        with pytest.raises(ValidationError):
            BaseEvent(
                event_id="evt_003",
                event_type=EventTypeEnum.CREATED,
                source="",
            )

    def test_event_whitespace_source(self):
        """Test event with whitespace source."""
        with pytest.raises(ValidationError):
            BaseEvent(
                event_id="evt_004",
                event_type=EventTypeEnum.CREATED,
                source="   ",
            )

    def test_event_invalid_event_type(self):
        """Test event with invalid event type."""
        with pytest.raises(ValidationError):
            BaseEvent(
                event_id="evt_005",
                event_type="invalid_type",
                source="test_module",
            )

    def test_event_serialization(self):
        """Test event serialization to dict."""
        event = BaseEvent(
            event_id="evt_006",
            event_type=EventTypeEnum.UPDATED,
            source="test_module",
            payload={"key": "value"},
        )
        data = event.model_dump()
        assert data["event_id"] == "evt_006"
        assert data["event_type"] == "updated"
        assert data["source"] == "test_module"
        assert data["payload"] == {"key": "value"}

    def test_event_deserialization(self):
        """Test event deserialization from dict."""
        data = {
            "event_id": "evt_007",
            "event_type": "deleted",
            "source": "test_module",
            "payload": {"key": "value"},
        }
        event = BaseEvent(**data)
        assert event.event_id == "evt_007"
        assert event.event_type == EventTypeEnum.DELETED
        assert event.source == "test_module"


# =============================================================================
# ErrorResponse Tests
# =============================================================================

class TestErrorResponse:
    """Test ErrorResponse model."""

    def test_valid_error_response(self):
        """Test creating a valid error response."""
        error = ErrorResponse(
            error_code="NOT_FOUND",
            message="Resource not found",
        )
        assert error.status == StatusEnum.ERROR
        assert error.error_code == "NOT_FOUND"
        assert error.message == "Resource not found"
        assert error.details is None
        assert isinstance(error.timestamp, datetime)

    def test_error_response_with_details(self):
        """Test error response with details."""
        error = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message="Validation failed",
            details={"field": "name", "error": "required"},
        )
        assert error.details == {"field": "name", "error": "required"}

    def test_error_response_empty_code(self):
        """Test error response with empty error_code."""
        with pytest.raises(ValidationError):
            ErrorResponse(
                error_code="",
                message="Error message",
            )

    def test_error_response_whitespace_code(self):
        """Test error response with whitespace error_code."""
        with pytest.raises(ValidationError):
            ErrorResponse(
                error_code="   ",
                message="Error message",
            )

    def test_error_response_empty_message(self):
        """Test error response with empty message."""
        with pytest.raises(ValidationError):
            ErrorResponse(
                error_code="ERROR_CODE",
                message="",
            )

    def test_error_response_whitespace_message(self):
        """Test error response with whitespace message."""
        with pytest.raises(ValidationError):
            ErrorResponse(
                error_code="ERROR_CODE",
                message="   ",
            )

    def test_error_response_serialization(self):
        """Test error response serialization."""
        error = ErrorResponse(
            error_code="ERROR_CODE",
            message="Error message",
        )
        data = error.model_dump()
        assert data["status"] == "error"
        assert data["error_code"] == "ERROR_CODE"
        assert data["message"] == "Error message"


# =============================================================================
# SuccessResponse Tests
# =============================================================================

class TestSuccessResponse:
    """Test SuccessResponse model."""

    def test_valid_success_response(self):
        """Test creating a valid success response."""
        response = SuccessResponse(data={"key": "value"})
        assert response.status == StatusEnum.SUCCESS
        assert response.data == {"key": "value"}
        assert response.message is None

    def test_success_response_with_message(self):
        """Test success response with message."""
        response = SuccessResponse(
            data={"key": "value"},
            message="Operation successful",
        )
        assert response.message == "Operation successful"

    def test_success_response_no_data(self):
        """Test success response without data."""
        response = SuccessResponse()
        assert response.data is None
        assert response.status == StatusEnum.SUCCESS

    def test_success_response_serialization(self):
        """Test success response serialization."""
        response = SuccessResponse(data={"key": "value"})
        data = response.model_dump()
        assert data["status"] == "success"
        assert data["data"] == {"key": "value"}


# =============================================================================
# ValidationErrorResponse Tests
# =============================================================================

class TestValidationErrorResponse:
    """Test ValidationErrorResponse model."""

    def test_valid_validation_error(self):
        """Test creating a valid validation error response."""
        error = ValidationErrorResponse(
            errors=[{"field": "name", "error": "required"}]
        )
        assert error.status == StatusEnum.ERROR
        assert error.error_code == "VALIDATION_ERROR"
        assert error.message == "Validation failed"
        assert len(error.errors) == 1

    def test_validation_error_default_errors(self):
        """Test validation error with default errors list."""
        error = ValidationErrorResponse()
        assert error.errors == []

    def test_validation_error_custom_message(self):
        """Test validation error with custom message."""
        error = ValidationErrorResponse(
            message="Custom validation message",
            errors=[{"field": "email", "error": "invalid"}],
        )
        assert error.message == "Custom validation message"

    def test_validation_error_serialization(self):
        """Test validation error serialization."""
        error = ValidationErrorResponse(
            errors=[{"field": "name", "error": "required"}]
        )
        data = error.model_dump()
        assert data["error_code"] == "VALIDATION_ERROR"
        assert data["status"] == "error"
        assert len(data["errors"]) == 1


# =============================================================================
# PaginationParams Tests
# =============================================================================

class TestPaginationParams:
    """Test PaginationParams model."""

    def test_valid_pagination(self):
        """Test creating valid pagination params."""
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 20
        assert params.sort_by is None
        assert params.sort_order == "asc"

    def test_pagination_custom_values(self):
        """Test pagination with custom values."""
        params = PaginationParams(
            page=2,
            page_size=50,
            sort_by="name",
            sort_order="desc",
        )
        assert params.page == 2
        assert params.page_size == 50
        assert params.sort_by == "name"
        assert params.sort_order == "desc"

    def test_pagination_invalid_page(self):
        """Test pagination with invalid page."""
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

    def test_pagination_invalid_page_size(self):
        """Test pagination with invalid page_size."""
        with pytest.raises(ValidationError):
            PaginationParams(page_size=0)

    def test_pagination_page_size_too_large(self):
        """Test pagination with page_size too large."""
        with pytest.raises(ValidationError):
            PaginationParams(page_size=101)

    def test_pagination_invalid_sort_order(self):
        """Test pagination with invalid sort order."""
        with pytest.raises(ValidationError):
            PaginationParams(sort_order="invalid")


# =============================================================================
# PaginatedResponse Tests
# =============================================================================

class TestPaginatedResponse:
    """Test PaginatedResponse model."""

    def test_valid_paginated_response(self):
        """Test creating a valid paginated response."""
        response = PaginatedResponse[int](
            items=[1, 2, 3],
            total=3,
            page=1,
            page_size=10,
            total_pages=1,
        )
        assert response.items == [1, 2, 3]
        assert response.total == 3
        assert response.page == 1
        assert response.page_size == 10
        assert response.total_pages == 1

    def test_paginated_response_multiple_pages(self):
        """Test paginated response with multiple pages."""
        response = PaginatedResponse[str](
            items=["a", "b"],
            total=25,
            page=2,
            page_size=10,
            total_pages=3,
        )
        assert response.total_pages == 3

    def test_paginated_response_invalid_total_pages(self):
        """Test paginated response with invalid total_pages."""
        with pytest.raises(ValidationError):
            PaginatedResponse[int](
                items=[1, 2, 3],
                total=3,
                page=1,
                page_size=10,
                total_pages=2,  # Should be 1
            )

    def test_paginated_response_empty_items(self):
        """Test paginated response with empty items."""
        response = PaginatedResponse[int](
            items=[],
            total=0,
            page=1,
            page_size=10,
            total_pages=0,
        )
        assert response.items == []
        assert response.total == 0
        assert response.total_pages == 0


# =============================================================================
# BaseEntity Tests
# =============================================================================

class TestBaseEntity:
    """Test BaseEntity model."""

    def test_valid_entity(self):
        """Test creating a valid entity."""
        entity = BaseEntity(id="ent_001")
        assert entity.id == "ent_001"
        assert entity.status == StatusEnum.ACTIVE
        assert isinstance(entity.created_at, datetime)
        assert isinstance(entity.updated_at, datetime)

    def test_entity_custom_status(self):
        """Test entity with custom status."""
        entity = BaseEntity(id="ent_002", status=StatusEnum.PENDING)
        assert entity.status == StatusEnum.PENDING

    def test_entity_empty_id(self):
        """Test entity with empty id."""
        with pytest.raises(ValidationError):
            BaseEntity(id="")

    def test_entity_whitespace_id(self):
        """Test entity with whitespace id."""
        with pytest.raises(ValidationError):
            BaseEntity(id="   ")

    def test_entity_serialization(self):
        """Test entity serialization."""
        entity = BaseEntity(id="ent_003")
        data = entity.model_dump()
        assert data["id"] == "ent_003"
        assert data["status"] == "active"


# =============================================================================
# HealthResponse Tests
# =============================================================================

class TestHealthResponse:
    """Test HealthResponse model."""

    def test_valid_health_response(self):
        """Test creating a valid health response."""
        health = HealthResponse()
        assert health.status == "ok"
        assert health.version == "1.0.0"
        assert isinstance(health.timestamp, datetime)

    def test_health_response_custom_version(self):
        """Test health response with custom version."""
        health = HealthResponse(version="2.0.0")
        assert health.version == "2.0.0"

    def test_health_response_serialization(self):
        """Test health response serialization."""
        health = HealthResponse()
        data = health.model_dump()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Test helper functions."""

    def test_create_success_response(self):
        """Test create_success_response function."""
        response = create_success_response(data={"key": "value"})
        assert isinstance(response, SuccessResponse)
        assert response.data == {"key": "value"}
        assert response.status == StatusEnum.SUCCESS

    def test_create_success_response_with_message(self):
        """Test create_success_response with message."""
        response = create_success_response(
            data={"key": "value"},
            message="Success",
        )
        assert response.message == "Success"

    def test_create_error_response(self):
        """Test create_error_response function."""
        response = create_error_response(
            error_code="ERROR_CODE",
            message="Error message",
        )
        assert isinstance(response, ErrorResponse)
        assert response.error_code == "ERROR_CODE"
        assert response.message == "Error message"

    def test_create_error_response_with_details(self):
        """Test create_error_response with details."""
        response = create_error_response(
            error_code="ERROR_CODE",
            message="Error message",
            details={"field": "error"},
        )
        assert response.details == {"field": "error"}

    def test_create_validation_error_response(self):
        """Test create_validation_error_response function."""
        errors = [{"field": "name", "error": "required"}]
        response = create_validation_error_response(errors=errors)
        assert isinstance(response, ValidationErrorResponse)
        assert response.errors == errors

    def test_create_validation_error_response_custom_message(self):
        """Test create_validation_error_response with custom message."""
        errors = [{"field": "name", "error": "required"}]
        response = create_validation_error_response(
            errors=errors,
            message="Custom message",
        )
        assert response.message == "Custom message"

    def test_create_health_response(self):
        """Test create_health_response function."""
        response = create_health_response()
        assert isinstance(response, HealthResponse)
        assert response.status == "ok"

    def test_create_health_response_custom_version(self):
        """Test create_health_response with custom version."""
        response = create_health_response(version="2.0.0")
        assert response.version == "2.0.0"

    def test_validate_event_valid(self):
        """Test validate_event with valid event."""
        event = BaseEvent(
            event_id="evt_001",
            event_type=EventTypeEnum.CREATED,
            source="test",
        )
        assert validate_event(event) is True

    def test_validate_event_invalid(self):
        """Test validate_event with invalid event."""
        with pytest.raises(ValidationError):
            BaseEvent(
                event_id="",
                event_type=EventTypeEnum.CREATED,
                source="test",
            )


# =============================================================================
# API Tests
# =============================================================================

class TestAPI:
    """Test FastAPI endpoints."""

    def test_health_endpoint(self, client):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert "timestamp" in data

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "enterprise_core"
        assert data["version"] == "1.0.0"
        assert data["status"] == "running"

    def test_health_endpoint_response_model(self, client):
        """Test health endpoint response model."""
        response = client.get("/health")
        assert response.status_code == 200
        # Validate response against HealthResponse model
        health = HealthResponse(**response.json())
        assert health.status == "ok"
        assert health.version == "1.0.0"


# =============================================================================
# Serialization/Deserialization Tests
# =============================================================================

class TestSerialization:
    """Test serialization and deserialization."""

    def test_base_event_roundtrip(self):
        """Test BaseEvent serialization roundtrip."""
        event = BaseEvent(
            event_id="evt_001",
            event_type=EventTypeEnum.CREATED,
            source="test",
            payload={"key": "value"},
        )
        data = event.model_dump()
        event2 = BaseEvent(**data)
        assert event2 == event

    def test_error_response_roundtrip(self):
        """Test ErrorResponse serialization roundtrip."""
        error = ErrorResponse(
            error_code="ERROR",
            message="Error message",
            details={"field": "error"},
        )
        data = error.model_dump()
        error2 = ErrorResponse(**data)
        assert error2 == error

    def test_success_response_roundtrip(self):
        """Test SuccessResponse serialization roundtrip."""
        response = SuccessResponse(
            data={"key": "value"},
            message="Success",
        )
        data = response.model_dump()
        response2 = SuccessResponse(**data)
        assert response2 == response

    def test_validation_error_roundtrip(self):
        """Test ValidationErrorResponse serialization roundtrip."""
        error = ValidationErrorResponse(
            errors=[{"field": "name", "error": "required"}],
        )
        data = error.model_dump()
        error2 = ValidationErrorResponse(**data)
        assert error2 == error

    def test_pagination_params_roundtrip(self):
        """Test PaginationParams serialization roundtrip."""
        params = PaginationParams(
            page=2,
            page_size=50,
            sort_by="name",
            sort_order="desc",
        )
        data = params.model_dump()
        params2 = PaginationParams(**data)
        assert params2 == params

    def test_base_entity_roundtrip(self):
        """Test BaseEntity serialization roundtrip."""
        entity = BaseEntity(id="ent_001", status=StatusEnum.PENDING)
        data = entity.model_dump()
        entity2 = BaseEntity(**data)
        assert entity2 == entity

    def test_health_response_roundtrip(self):
        """Test HealthResponse serialization roundtrip."""
        health = HealthResponse(version="2.0.0")
        data = health.model_dump()
        health2 = HealthResponse(**data)
        assert health2 == health