# actions/enterprise_schema_registry/test_enterprise_schema_registry.py
import pytest
from fastapi.testclient import TestClient

from actions.enterprise_schema_registry.enterprise_schema_registry import SchemaRegistry
from actions.enterprise_schema_registry.main import app

client = TestClient(app)


# --- Unit tests for SchemaRegistry class ---

class TestSchemaRegistry:
    def setup_method(self):
        self.registry = SchemaRegistry()

    def test_register_and_get(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        self.registry.register("person", 1, schema)
        assert self.registry.get("person", 1) == schema

    def test_register_duplicate_version_raises(self):
        schema = {"type": "object"}
        self.registry.register("person", 1, schema)
        with pytest.raises(ValueError):
            self.registry.register("person", 1, schema)

    def test_get_nonexistent_returns_none(self):
        assert self.registry.get("nonexistent", 1) is None

    def test_validate_valid_data(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        self.registry.register("person", 1, schema)
        errors = self.registry.validate("person", 1, {"name": "Alice"})
        assert errors == []

    def test_validate_invalid_data(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        self.registry.register("person", 1, schema)
        errors = self.registry.validate("person", 1, {"age": 30})
        assert len(errors) > 0

    def test_validate_nonexistent_schema_raises(self):
        with pytest.raises(KeyError):
            self.registry.validate("nonexistent", 1, {})


# --- FastAPI endpoint tests ---

class TestSchemaRegistryAPI:
    def setup_method(self):
        # Clear registry before each test
        app.state.registry = SchemaRegistry()
        # Override the global registry reference
        import actions.enterprise_schema_registry.main as main_module
        main_module.registry = app.state.registry

    def test_register_schema_endpoint(self):
        response = client.post("/schemas", json={
            "name": "person",
            "version": 1,
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}}
        })
        assert response.status_code == 200
        assert response.json() == {"name": "person", "version": 1, "message": "Schema registered successfully"}

    def test_register_duplicate_schema_endpoint(self):
        client.post("/schemas", json={
            "name": "person",
            "version": 1,
            "schema": {"type": "object"}
        })
        response = client.post("/schemas", json={
            "name": "person",
            "version": 1,
            "schema": {"type": "object"}
        })
        assert response.status_code == 409

    def test_get_schema_endpoint(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        client.post("/schemas", json={"name": "person", "version": 1, "schema": schema})
        response = client.get("/schemas/person/1")
        assert response.status_code == 200
        assert response.json() == {"name": "person", "version": 1, "schema": schema}

    def test_get_nonexistent_schema_endpoint(self):
        response = client.get("/schemas/nonexistent/1")
        assert response.status_code == 404

    def test_validate_valid_data_endpoint(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        client.post("/schemas", json={"name": "person", "version": 1, "schema": schema})
        response = client.post("/validate/person/1", json={"data": {"name": "Alice"}})
        assert response.status_code == 200
        assert response.json() == {"valid": True, "errors": None}

    def test_validate_invalid_data_endpoint(self):
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        client.post("/schemas", json={"name": "person", "version": 1, "schema": schema})
        response = client.post("/validate/person/1", json={"data": {"age": 30}})
        assert response.status_code == 200
        assert response.json()["valid"] is False
        assert len(response.json()["errors"]) > 0

    def test_validate_nonexistent_schema_endpoint(self):
        response = client.post("/validate/nonexistent/1", json={"data": {}})
        assert response.status_code == 404