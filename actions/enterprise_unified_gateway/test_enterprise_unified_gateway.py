"""
Pytest tests for the Enterprise Unified Gateway module.
"""

from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from actions.enterprise_unified_gateway.enterprise_unified_gateway import GatewayRouter
from actions.enterprise_unified_gateway.main import app, gateway_router
from actions.enterprise_unified_gateway.schemas import RoutePayload, RouteResponse


@pytest.fixture
def client() -> TestClient:
    """Fixture to create a TestClient for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_registry():
    """Fixture to clean the service registry before and after each test."""
    # Clean before test
    for service in list(gateway_router.get_registered_services()):
        gateway_router.unregister_service(service)
    yield
    # Clean after test
    for service in list(gateway_router.get_registered_services()):
        gateway_router.unregister_service(service)


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    def test_health_check(self, client: TestClient):
        """Test that the health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "enterprise_unified_gateway"


class TestGatewayRouter:
    """Tests for the GatewayRouter class."""

    def test_register_service(self):
        """Test registering a new service."""
        router = GatewayRouter()

        def handler(payload: RoutePayload) -> Dict[str, Any]:
            return {"message": "test"}

        router.register_service("test_service", handler)
        assert router.is_service_registered("test_service")
        assert "test_service" in router.get_registered_services()

    def test_register_duplicate_service(self):
        """Test registering a duplicate service raises ValueError."""
        router = GatewayRouter()

        def handler(payload: RoutePayload) -> Dict[str, Any]:
            return {"message": "test"}

        router.register_service("test_service", handler)
        with pytest.raises(ValueError, match="already registered"):
            router.register_service("test_service", handler)

    def test_unregister_service(self):
        """Test unregistering a service."""
        router = GatewayRouter()

        def handler(payload: RoutePayload) -> Dict[str, Any]:
            return {"message": "test"}

        router.register_service("test_service", handler)
        assert router.unregister_service("test_service") is True
        assert not router.is_service_registered("test_service")

    def test_unregister_nonexistent_service(self):
        """Test unregistering a non-existent service returns False."""
        router = GatewayRouter()
        assert router.unregister_service("nonexistent") is False

    def test_route_to_registered_service(self):
        """Test routing to a registered service."""
        router = GatewayRouter()

        def handler(payload: RoutePayload) -> Dict[str, Any]:
            return {"message": f"Processed {payload.service_name}"}

        router.register_service("test_service", handler)
        payload = RoutePayload(service_name="test_service")
        response = router.route(payload)

        assert response.success is True
        assert response.status_code == 200
        assert response.data == {"message": "Processed test_service"}

    def test_route_to_unregistered_service(self):
        """Test routing to an unregistered service returns 404."""
        router = GatewayRouter()
        payload = RoutePayload(service_name="nonexistent")
        response = router.route(payload)

        assert response.success is False
        assert response.status_code == 404
        assert "not found" in response.error

    def test_route_with_handler_error(self):
        """Test routing when handler raises an exception."""
        router = GatewayRouter()

        def failing_handler(payload: RoutePayload) -> Dict[str, Any]:
            raise RuntimeError("Handler failed")

        router.register_service("failing_service", failing_handler)
        payload = RoutePayload(service_name="failing_service")
        response = router.route(payload)

        assert response.success is False
        assert response.status_code == 500
        assert "Internal error" in response.error


class TestRouteEndpoint:
    """Tests for the /route/{service_name} endpoint."""

    def test_route_to_registered_service(self, client: TestClient):
        """Test successful routing to a registered service."""
        # Register a test service
        response = client.post("/register/test_service")
        assert response.status_code == 200

        # Route to the service
        response = client.post(
            "/route/test_service",
            json={"message": "hello"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["service_name"] == "test_service"
        assert data["status_code"] == 200
        assert data["data"]["message"] == "Service 'test_service' processed the request"

    def test_route_to_unregistered_service(self, client: TestClient):
        """Test routing to an unregistered service returns 404."""
        response = client.post(
            "/route/nonexistent_service",
            json={"message": "hello"},
        )
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"]

    def test_route_with_empty_body(self, client: TestClient):
        """Test routing with an empty body."""
        # Register a test service
        client.post("/register/test_service")

        # Route with empty body
        response = client.post("/route/test_service")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["body"] == {}

    def test_route_with_query_params(self, client: TestClient):
        """Test routing with query parameters."""
        # Register a test service
        client.post("/register/test_service")

        # Route with query parameters
        response = client.post("/route/test_service?param1=value1&param2=value2")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["body"] == {}


class TestServicesEndpoint:
    """Tests for the /services endpoint."""

    def test_list_services_empty(self, client: TestClient):
        """Test listing services when none are registered."""
        response = client.get("/services")
        assert response.status_code == 200
        data = response.json()
        assert data["services"] == []

    def test_list_services_with_registered(self, client: TestClient):
        """Test listing services after registration."""
        client.post("/register/service1")
        client.post("/register/service2")

        response = client.get("/services")
        assert response.status_code == 200
        data = response.json()
        assert "service1" in data["services"]
        assert "service2" in data["services"]


class TestRegisterEndpoint:
    """Tests for the /register/{service_name} endpoint."""

    def test_register_new_service(self, client: TestClient):
        """Test registering a new service."""
        response = client.post("/register/new_service")
        assert response.status_code == 200
        data = response.json()
        assert "registered successfully" in data["message"]

    def test_register_duplicate_service(self, client: TestClient):
        """Test registering a duplicate service returns 400."""
        client.post("/register/dup_service")
        response = client.post("/register/dup_service")
        assert response.status_code == 400
        data = response.json()
        assert "already registered" in data["detail"]


class TestRoutePayloadSchema:
    """Tests for the RoutePayload schema."""

    def test_route_payload_defaults(self):
        """Test RoutePayload with default values."""
        payload = RoutePayload(service_name="test")
        assert payload.method == "GET"
        assert payload.path == "/"
        assert payload.headers == {}
        assert payload.body == {}
        assert payload.query_params == {}

    def test_route_payload_custom_values(self):
        """Test RoutePayload with custom values."""
        payload = RoutePayload(
            service_name="test",
            method="POST",
            path="/custom",
            headers={"Content-Type": "application/json"},
            body={"key": "value"},
            query_params={"param": "value"},
        )
        assert payload.method == "POST"
        assert payload.path == "/custom"
        assert payload.headers == {"Content-Type": "application/json"}
        assert payload.body == {"key": "value"}
        assert payload.query_params == {"param": "value"}

    def test_route_payload_required_field(self):
        """Test RoutePayload requires service_name."""
        with pytest.raises(ValueError):
            RoutePayload()


class TestRouteResponseSchema:
    """Tests for the RouteResponse schema."""

    def test_route_response_success(self):
        """Test RouteResponse for successful routing."""
        response = RouteResponse(
            success=True,
            service_name="test",
            status_code=200,
            data={"message": "success"},
        )
        assert response.success is True
        assert response.service_name == "test"
        assert response.status_code == 200
        assert response.data == {"message": "success"}
        assert response.error is None

    def test_route_response_error(self):
        """Test RouteResponse for error routing."""
        response = RouteResponse(
            success=False,
            service_name="test",
            status_code=404,
            error="Service not found",
        )
        assert response.success is False
        assert response.service_name == "test"
        assert response.status_code == 404
        assert response.error == "Service not found"
        assert response.data is None