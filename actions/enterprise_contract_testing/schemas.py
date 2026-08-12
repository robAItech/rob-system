"""Pydantic schemas for the enterprise contract testing module."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


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