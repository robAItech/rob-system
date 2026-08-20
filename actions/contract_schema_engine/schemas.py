"""
Pydantic schemas for the unified contract-schema engine.

Združitev shem nekdanjih modulov:
- ``schema_registry`` — runtime JSON Schema validacija.
- ``contract_testing`` — Consumer-Driven Contract (CDC) generacija/verifikacija.
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


# ── Schema registry (runtime JSON Schema) ─────────────────────────────────────

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


# ── Contract testing (CDC) ────────────────────────────────────────────────────

class ContractGenerateRequest(BaseModel):
    """Request schema for generating a contract."""
    service_name: str = Field(..., min_length=1, description="Name of the service")
    schema: Dict[str, Any] = Field(..., description="JSON schema for the contract")


class ContractGenerateResponse(BaseModel):
    """Response schema for generating a contract."""
    contract_id: str
    service_name: str
    schema: Dict[str, Any]
    version: str
    checksum: str
    created_at: str


class ContractVerifyRequest(BaseModel):
    """Request schema for verifying a contract."""
    consumer_schema: Dict[str, Any] = Field(..., description="Consumer's expected schema")
    provider_schema: Dict[str, Any] = Field(..., description="Provider's actual schema")


class ContractVerifyResponse(BaseModel):
    """Response schema for verifying a contract."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ContractInfo(BaseModel):
    """Schema for contract information."""
    contract_id: str
    service_name: str
    schema: Dict[str, Any]
    version: str
    checksum: str
    created_at: str
