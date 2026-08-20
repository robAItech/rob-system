"""
Pydantic schemas for api_versioning module.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class VersionInfo(BaseModel):
    """Schema for version information response."""
    current_version: str
    supported_versions: list[str]
    deprecated_versions: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Schema for health check response."""
    status: str = "ok"
    version: str
    service: str = "enterprise-api-versioning"