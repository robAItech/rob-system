# actions/schema_registry/schema_registry.py
import json
import logging
from typing import Any, Dict, Optional

from jsonschema import Draft7Validator, ValidationError

logger = logging.getLogger(__name__)


class SchemaRegistry:
    """A simple in-memory schema registry with validation capabilities."""

    def __init__(self) -> None:
        self._schemas: Dict[str, Dict[int, Dict[str, Any]]] = {}

    def register(self, name: str, version: int, schema: Dict[str, Any]) -> None:
        """Register a new schema version."""
        if name not in self._schemas:
            self._schemas[name] = {}
        if version in self._schemas[name]:
            raise ValueError(f"Schema '{name}' version {version} already exists")
        self._schemas[name][version] = schema
        logger.info("Registered schema '%s' version %d", name, version)

    def get(self, name: str, version: int) -> Optional[Dict[str, Any]]:
        """Retrieve a schema by name and version."""
        return self._schemas.get(name, {}).get(version)

    def validate(self, name: str, version: int, data: Dict[str, Any]) -> list:
        """Validate data against a schema. Returns list of errors (empty if valid)."""
        schema = self.get(name, version)
        if schema is None:
            raise KeyError(f"Schema '{name}' version {version} not found")

        validator = Draft7Validator(schema)
        errors = []
        for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            errors.append({
                "path": list(error.path),
                "message": error.message,
                "validator": error.validator,
            })
        return errors

    def list_schemas(self) -> Dict[str, list]:
        """List all registered schemas with their versions."""
        return {name: sorted(versions.keys()) for name, versions in self._schemas.items()}