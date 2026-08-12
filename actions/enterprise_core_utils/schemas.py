"""
Pydantic schemas for the enterprise_core_utils module.

These schemas define the data structures used by the FastAPI endpoints
and provide validation for API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Optional


class HealthResponse(BaseModel):
    """Response schema for the health check endpoint."""

    status: str = Field(..., description="Service status")
    timestamp: str = Field(..., description="UTC timestamp in ISO 8601 format")
    version: str = Field(..., description="Module version")


class RootResponse(BaseModel):
    """Response schema for the root endpoint."""

    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Module version")
    message: str = Field(..., description="Welcome message")