"""Pytest tests for the enterprise contract testing module."""

import pytest
from fastapi.testclient import TestClient

from actions.contract_schema_engine.contracts import ContractManager
from actions.contract_schema_engine.main import app

client = TestClient(app)


@pytest.fixture
def valid_consumer_schema():
    """Fixture providing a valid consumer schema."""
    return {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "email": {"type": "string"},
            "address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                },
                "required": ["street", "city"],
            },
        },
        "required": ["id", "name", "email"],
    }


@pytest.fixture
def valid_provider_schema():
    """Fixture providing a valid provider schema with extra fields."""
    return {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "name": {"type": "string"},
            "email": {"type": "string"},
            "address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                    "zip": {"type": "string"},
                },
                "required": ["street", "city", "zip"],
            },
            "phone": {"type": "string"},
        },
        "required": ["id", "name", "email", "address"],
    }


@pytest.fixture
def incompatible_provider_schema():
    """Fixture providing an incompatible provider schema."""
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string"},  # Wrong type
            "name": {"type": "string"},
            "address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                },
                "required": ["street"],
            },
        },
        "required": ["id", "name"],
    }


class TestContractManager:
    """Test cases for ContractManager class."""

    def test_generate_contract_success(self):
        """Test successful contract generation."""
        manager = ContractManager()
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        contract = manager.generate_contract("test-service", schema)

        assert contract["service_name"] == "test-service"
        assert contract["schema"] == schema
        assert contract["version"] == "1.0.0"
        assert "contract_id" in contract
        assert "checksum" in contract
        assert "created_at" in contract

    def test_generate_contract_empty_service_name(self):
        """Test contract generation with empty service name."""
        manager = ContractManager()
        schema = {"type": "object", "properties": {}}

        with pytest.raises(ValueError, match="Service name must be a non-empty string"):
            manager.generate_contract("", schema)

    def test_generate_contract_invalid_schema(self):
        """Test contract generation with invalid schema."""
        manager = ContractManager()

        with pytest.raises(ValueError, match="Schema must be a non-empty dictionary"):
            manager.generate_contract("test-service", {})

    def test_generate_contract_missing_type(self):
        """Test contract generation with schema missing type."""
        manager = ContractManager()
        schema = {"properties": {}}

        with pytest.raises(ValueError, match="Schema must have a 'type' field"):
            manager.generate_contract("test-service", schema)

    def test_generate_contract_invalid_type(self):
        """Test contract generation with invalid schema type."""
        manager = ContractManager()
        schema = {"type": "string", "properties": {}}

        with pytest.raises(ValueError, match="Schema type must be 'object'"):
            manager.generate_contract("test-service", schema)

    def test_generate_contract_missing_properties(self):
        """Test contract generation with schema missing properties."""
        manager = ContractManager()
        schema = {"type": "object"}

        with pytest.raises(ValueError, match="Schema must have 'properties' field"):
            manager.generate_contract("test-service", schema)

    def test_generate_contract_required_not_in_properties(self):
        """Test contract generation with required field not in properties."""
        manager = ContractManager()
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["email"],
        }

        with pytest.raises(ValueError, match="Required field 'email' not found in properties"):
            manager.generate_contract("test-service", schema)

    def test_verify_contract_success(self, valid_consumer_schema, valid_provider_schema):
        """Test successful contract verification."""
        manager = ContractManager()

        is_valid, errors, warnings = manager.verify_contract(
            valid_consumer_schema, valid_provider_schema
        )

        assert is_valid is True
        assert errors == []
        assert len(warnings) > 0  # Provider has extra fields

    def test_verify_contract_missing_required_field(self, valid_consumer_schema):
        """Test verification with missing required field."""
        manager = ContractManager()
        provider_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
            },
            "required": ["id", "name"],
        }

        is_valid, errors, warnings = manager.verify_contract(
            valid_consumer_schema, provider_schema
        )

        assert is_valid is False
        assert any("Missing required field 'email'" in error for error in errors)

    def test_verify_contract_type_mismatch(self, valid_consumer_schema):
        """Test verification with type mismatch."""
        manager = ContractManager()
        provider_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},  # Wrong type
                "name": {"type": "string"},
                "email": {"type": "string"},
            },
            "required": ["id", "name", "email"],
        }

        is_valid, errors, warnings = manager.verify_contract(
            valid_consumer_schema, provider_schema
        )

        assert is_valid is False
        assert any("Type mismatch for field 'id'" in error for error in errors)

    def test_verify_contract_nested_missing_field(self, valid_consumer_schema):
        """Test verification with missing nested field."""
        manager = ContractManager()
        provider_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "email": {"type": "string"},
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        # Missing 'city'
                    },
                    "required": ["street"],
                },
            },
            "required": ["id", "name", "email", "address"],
        }

        is_valid, errors, warnings = manager.verify_contract(
            valid_consumer_schema, provider_schema
        )

        assert is_valid is False
        assert any("Missing nested field 'address.city'" in error for error in errors)

    def test_verify_contract_enum_mismatch(self):
        """Test verification with enum mismatch."""
        manager = ContractManager()
        consumer_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive", "pending"]}
            },
            "required": ["status"],
        }
        provider_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive"]}
            },
            "required": ["status"],
        }

        is_valid, errors, warnings = manager.verify_contract(
            consumer_schema, provider_schema
        )

        assert is_valid is False
        assert any("missing enum values" in error for error in errors)

    def test_verify_contract_array_type_mismatch(self):
        """Test verification with array type mismatch."""
        manager = ContractManager()
        consumer_schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["tags"],
        }
        provider_schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}}
            },
            "required": ["tags"],
        }

        is_valid, errors, warnings = manager.verify_contract(
            consumer_schema, provider_schema
        )

        assert is_valid is False
        assert any("Array item type mismatch" in error for error in errors)

    def test_verify_contract_invalid_consumer_schema(self):
        """Test verification with invalid consumer schema."""
        manager = ContractManager()
        provider_schema = {"type": "object", "properties": {}}

        with pytest.raises(ValueError, match="Consumer schema must be a non-empty dictionary"):
            manager.verify_contract({}, provider_schema)

    def test_verify_contract_invalid_provider_schema(self):
        """Test verification with invalid provider schema."""
        manager = ContractManager()
        consumer_schema = {"type": "object", "properties": {}}

        with pytest.raises(ValueError, match="Provider schema must be a non-empty dictionary"):
            manager.verify_contract(consumer_schema, {})

    def test_get_contract_success(self):
        """Test retrieving a contract."""
        manager = ContractManager()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        contract = manager.generate_contract("test-service", schema)

        retrieved = manager.get_contract(contract["contract_id"])

        assert retrieved == contract

    def test_get_contract_not_found(self):
        """Test retrieving a non-existent contract."""
        manager = ContractManager()

        with pytest.raises(KeyError, match="Contract 'nonexistent' not found"):
            manager.get_contract("nonexistent")

    def test_list_contracts(self):
        """Test listing contracts."""
        manager = ContractManager()
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        manager.generate_contract("service1", schema)
        manager.generate_contract("service2", schema)

        contracts = manager.list_contracts()

        assert len(contracts) == 2


class TestContractAPI:
    """Test cases for FastAPI endpoints."""

    def test_generate_contract_endpoint_success(self):
        """Test contract generation endpoint."""
        request_data = {
            "service_name": "test-service",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
        }

        response = client.post("/contracts/generate", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["service_name"] == "test-service"
        assert "contract_id" in data
        assert "checksum" in data

    def test_generate_contract_endpoint_invalid_service_name(self):
        """Test contract generation with invalid service name."""
        request_data = {
            "service_name": "",
            "schema": {"type": "object", "properties": {}},
        }

        response = client.post("/contracts/generate", json=request_data)

        assert response.status_code == 422

    def test_generate_contract_endpoint_invalid_schema(self):
        """Test contract generation with invalid schema."""
        request_data = {
            "service_name": "test-service",
            "schema": {"type": "string", "properties": {}},
        }

        response = client.post("/contracts/generate", json=request_data)

        assert response.status_code == 400

    def test_verify_contract_endpoint_success(self, valid_consumer_schema, valid_provider_schema):
        """Test successful contract verification endpoint."""
        request_data = {
            "consumer_schema": valid_consumer_schema,
            "provider_schema": valid_provider_schema,
        }

        response = client.post("/contracts/verify", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []
        assert len(data["warnings"]) > 0

    def test_verify_contract_endpoint_incompatible(self, valid_consumer_schema, incompatible_provider_schema):
        """Test verification with incompatible schemas."""
        request_data = {
            "consumer_schema": valid_consumer_schema,
            "provider_schema": incompatible_provider_schema,
        }

        response = client.post("/contracts/verify", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_verify_contract_endpoint_missing_required(self, valid_consumer_schema):
        """Test verification with missing required field."""
        provider_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
            },
            "required": ["id", "name"],
        }

        request_data = {
            "consumer_schema": valid_consumer_schema,
            "provider_schema": provider_schema,
        }

        response = client.post("/contracts/verify", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("Missing required field 'email'" in error for error in data["errors"])

    def test_verify_contract_endpoint_type_mismatch(self, valid_consumer_schema):
        """Test verification with type mismatch."""
        provider_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},  # Wrong type
                "name": {"type": "string"},
                "email": {"type": "string"},
            },
            "required": ["id", "name", "email"],
        }

        request_data = {
            "consumer_schema": valid_consumer_schema,
            "provider_schema": provider_schema,
        }

        response = client.post("/contracts/verify", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("Type mismatch for field 'id'" in error for error in data["errors"])

    def test_verify_contract_endpoint_invalid_consumer(self):
        """Test verification with invalid consumer schema."""
        request_data = {
            "consumer_schema": {},
            "provider_schema": {"type": "object", "properties": {}},
        }

        response = client.post("/contracts/verify", json=request_data)

        assert response.status_code == 400

    def test_list_contracts_endpoint(self):
        """Test listing contracts endpoint."""
        # Generate a contract first
        request_data = {
            "service_name": "list-test-service",
            "schema": {"type": "object", "properties": {"name": {"type": "string"}}},
        }
        client.post("/contracts/generate", json=request_data)

        response = client.get("/contracts")

        assert response.status_code == 200
        contracts = response.json()
        assert len(contracts) >= 1
        assert any(contract["service_name"] == "list-test-service" for contract in contracts)

    def test_health_check_endpoint(self):
        """Test health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "version": "1.0.0"}

    def test_verify_contract_endpoint_nested_missing(self, valid_consumer_schema):
        """Test verification with missing nested field."""
        provider_schema = {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "email": {"type": "string"},
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                    },
                    "required": ["street"],
                },
            },
            "required": ["id", "name", "email", "address"],
        }

        request_data = {
            "consumer_schema": valid_consumer_schema,
            "provider_schema": provider_schema,
        }

        response = client.post("/contracts/verify", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("Missing nested field 'address.city'" in error for error in data["errors"])

    def test_verify_contract_endpoint_enum_mismatch(self):
        """Test verification with enum mismatch."""
        consumer_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive", "pending"]}
            },
            "required": ["status"],
        }
        provider_schema = {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "inactive"]}
            },
            "required": ["status"],
        }

        request_data = {
            "consumer_schema": consumer_schema,
            "provider_schema": provider_schema,
        }

        response = client.post("/contracts/verify", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("missing enum values" in error for error in data["errors"])

    def test_verify_contract_endpoint_array_mismatch(self):
        """Test verification with array type mismatch."""
        consumer_schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["tags"],
        }
        provider_schema = {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "integer"}}
            },
            "required": ["tags"],
        }

        request_data = {
            "consumer_schema": consumer_schema,
            "provider_schema": provider_schema,
        }

        response = client.post("/contracts/verify", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("Array item type mismatch" in error for error in data["errors"])