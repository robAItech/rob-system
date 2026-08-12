"""Core logic for Consumer-Driven Contract (CDC) validation."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


class ContractManager:
    """Manages contract generation and verification."""

    def __init__(self) -> None:
        """Initialize the contract manager with an empty contract store."""
        self._contracts: Dict[str, Dict[str, Any]] = {}

    def generate_contract(self, service_name: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a contract for a given service and schema.

        Args:
            service_name: Name of the service.
            schema: JSON schema for the contract.

        Returns:
            A dictionary containing the generated contract.

        Raises:
            ValueError: If service_name is empty or schema is invalid.
        """
        if not service_name or not service_name.strip():
            raise ValueError("Service name must be a non-empty string")

        if not isinstance(schema, dict) or not schema:
            raise ValueError("Schema must be a non-empty dictionary")

        if "type" not in schema:
            raise ValueError("Schema must have a 'type' field")

        if schema["type"] != "object":
            raise ValueError("Schema type must be 'object'")

        if "properties" not in schema:
            raise ValueError("Schema must have 'properties' field")

        if not isinstance(schema["properties"], dict):
            raise ValueError("Schema 'properties' must be a dictionary")

        required = schema.get("required", [])
        if not isinstance(required, list):
            raise ValueError("Schema 'required' must be a list")

        for field in required:
            if field not in schema["properties"]:
                raise ValueError(f"Required field '{field}' not found in properties")

        contract_id = str(uuid.uuid4())
        checksum = self._calculate_checksum(schema)
        created_at = datetime.now(timezone.utc).isoformat()

        contract = {
            "contract_id": contract_id,
            "service_name": service_name,
            "schema": schema,
            "version": "1.0.0",
            "checksum": checksum,
            "created_at": created_at,
        }

        self._contracts[contract_id] = contract
        return contract

    def verify_contract(
        self, consumer_schema: Dict[str, Any], provider_schema: Dict[str, Any]
    ) -> Tuple[bool, List[str], List[str]]:
        """Verify that a provider schema satisfies the consumer's requirements.

        Args:
            consumer_schema: The consumer's expected schema.
            provider_schema: The provider's actual schema.

        Returns:
            A tuple of (is_valid, errors, warnings).

        Raises:
            ValueError: If either schema is invalid.
        """
        if not isinstance(consumer_schema, dict) or not consumer_schema:
            raise ValueError("Consumer schema must be a non-empty dictionary")

        if not isinstance(provider_schema, dict) or not provider_schema:
            raise ValueError("Provider schema must be a non-empty dictionary")

        errors: List[str] = []
        warnings: List[str] = []

        # Validate top-level schemas
        if "type" not in consumer_schema:
            raise ValueError("Consumer schema must have a 'type' field")
        if "type" not in provider_schema:
            raise ValueError("Provider schema must have a 'type' field")

        if consumer_schema["type"] != "object":
            raise ValueError("Consumer schema type must be 'object'")
        if provider_schema["type"] != "object":
            raise ValueError("Provider schema type must be 'object'")

        if "properties" not in consumer_schema:
            raise ValueError("Consumer schema must have 'properties' field")
        if "properties" not in provider_schema:
            raise ValueError("Provider schema must have 'properties' field")

        consumer_props = consumer_schema["properties"]
        provider_props = provider_schema["properties"]

        if not isinstance(consumer_props, dict):
            raise ValueError("Consumer schema 'properties' must be a dictionary")
        if not isinstance(provider_props, dict):
            raise ValueError("Provider schema 'properties' must be a dictionary")

        # Check required fields
        consumer_required = consumer_schema.get("required", [])
        if not isinstance(consumer_required, list):
            raise ValueError("Consumer schema 'required' must be a list")

        for field in consumer_required:
            if field not in provider_props:
                errors.append(f"Missing required field '{field}'")

        # Check field types and nested structures
        for field, consumer_field_schema in consumer_props.items():
            if field not in provider_props:
                if field in consumer_required:
                    errors.append(f"Missing required field '{field}'")
                else:
                    warnings.append(f"Optional field '{field}' missing in provider")
                continue

            provider_field_schema = provider_props[field]
            self._compare_field_schemas(
                field, consumer_field_schema, provider_field_schema, errors, warnings
            )

        # Check for extra fields in provider (warnings)
        for field in provider_props:
            if field not in consumer_props:
                warnings.append(f"Provider has extra field '{field}'")

        return len(errors) == 0, errors, warnings

    def get_contract(self, contract_id: str) -> Dict[str, Any]:
        """Retrieve a contract by ID.

        Args:
            contract_id: The contract ID.

        Returns:
            The contract dictionary.

        Raises:
            KeyError: If the contract is not found.
        """
        if contract_id not in self._contracts:
            raise KeyError(f"Contract '{contract_id}' not found")
        return self._contracts[contract_id]

    def list_contracts(self) -> List[Dict[str, Any]]:
        """List all stored contracts.

        Returns:
            A list of contract dictionaries.
        """
        return list(self._contracts.values())

    def _compare_field_schemas(
        self,
        field_name: str,
        consumer_schema: Dict[str, Any],
        provider_schema: Dict[str, Any],
        errors: List[str],
        warnings: List[str],
    ) -> None:
        """Compare field schemas between consumer and provider.

        Args:
            field_name: Name of the field being compared.
            consumer_schema: Consumer's field schema.
            provider_schema: Provider's field schema.
            errors: List to append errors to.
            warnings: List to append warnings to.
        """
        consumer_type = consumer_schema.get("type")
        provider_type = provider_schema.get("type")

        if consumer_type != provider_type:
            errors.append(
                f"Type mismatch for field '{field_name}': "
                f"consumer expects '{consumer_type}', provider has '{provider_type}'"
            )
            return

        # Check enum values
        if "enum" in consumer_schema:
            consumer_enum = set(consumer_schema["enum"])
            provider_enum = set(provider_schema.get("enum", []))
            missing_values = consumer_enum - provider_enum
            if missing_values:
                errors.append(
                    f"Field '{field_name}' is missing enum values: {sorted(missing_values)}"
                )

        # Check nested objects
        if consumer_type == "object":
            consumer_props = consumer_schema.get("properties", {})
            provider_props = provider_schema.get("properties", {})

            if not isinstance(consumer_props, dict) or not isinstance(provider_props, dict):
                errors.append(f"Field '{field_name}' has invalid properties structure")
                return

            consumer_required = consumer_schema.get("required", [])
            if not isinstance(consumer_required, list):
                errors.append(f"Field '{field_name}' has invalid required list")
                return

            for nested_field in consumer_required:
                if nested_field not in provider_props:
                    errors.append(
                        f"Missing nested field '{field_name}.{nested_field}'"
                    )

            for nested_field, nested_consumer_schema in consumer_props.items():
                if nested_field not in provider_props:
                    if nested_field in consumer_required:
                        errors.append(
                            f"Missing nested field '{field_name}.{nested_field}'"
                        )
                    else:
                        warnings.append(
                            f"Optional nested field '{field_name}.{nested_field}' missing in provider"
                        )
                    continue

                nested_provider_schema = provider_props[nested_field]
                self._compare_field_schemas(
                    f"{field_name}.{nested_field}",
                    nested_consumer_schema,
                    nested_provider_schema,
                    errors,
                    warnings,
                )

        # Check array items
        if consumer_type == "array":
            consumer_items = consumer_schema.get("items", {})
            provider_items = provider_schema.get("items", {})

            if not isinstance(consumer_items, dict) or not isinstance(provider_items, dict):
                errors.append(f"Field '{field_name}' has invalid items structure")
                return

            consumer_item_type = consumer_items.get("type")
            provider_item_type = provider_items.get("type")

            if consumer_item_type != provider_item_type:
                errors.append(
                    f"Array item type mismatch for field '{field_name}': "
                    f"consumer expects '{consumer_item_type}', provider has '{provider_item_type}'"
                )

    @staticmethod
    def _calculate_checksum(schema: Dict[str, Any]) -> str:
        """Calculate a checksum for a schema.

        Args:
            schema: The schema to calculate checksum for.

        Returns:
            A SHA-256 checksum string.
        """
        schema_json = json.dumps(schema, sort_keys=True, default=str)
        return hashlib.sha256(schema_json.encode()).hexdigest()