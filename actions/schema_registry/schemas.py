# actions/schema_registry/schemas.py
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional


class SchemaRegisterRequest(BaseModel):
    """Request model for registering a new schema."""
    name: str = Field(..., description="Name of the schema")
    version: int = Field(..., description="Version of the schema")
    schema: Dict[str, Any] = Field(..., description="The schema definition (JSON Schema)")


class SchemaRegisterResponse(BaseModel):
    """Response model for schema registration."""
    name: str
    version: int
    message: str = "Schema registered successfully"


class SchemaGetResponse(BaseModel):
    """Response model for retrieving a schema."""
    name: str
    version: int
    schema: Dict[str, Any]


class SchemaValidateRequest(BaseModel):
    """Request model for validating data against a schema."""
    data: Dict[str, Any] = Field(..., description="Data to validate against the schema")


class SchemaValidateResponse(BaseModel):
    """Response model for schema validation."""
    valid: bool
    errors: Optional[list] = None