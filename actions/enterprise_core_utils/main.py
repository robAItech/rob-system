"""
FastAPI application for the enterprise_core_utils module.

This module provides a minimal FastAPI application with health check
and root endpoints.
"""

from fastapi import FastAPI
from datetime import datetime, timezone

from actions.enterprise_core_utils.schemas import HealthResponse, RootResponse
from actions.enterprise_core_utils.enterprise_core_utils import TimestampNormalizer

app = FastAPI(
    title="Enterprise Core Utils API",
    description="Stateless utility functions for enterprise applications",
    version="1.0.0",
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns:
        HealthResponse with service status and current UTC timestamp
    """
    current_time = datetime.now(timezone.utc)
    return HealthResponse(
        status="healthy",
        timestamp=TimestampNormalizer.normalize(current_time),
        version="1.0.0",
    )


@app.get("/", response_model=RootResponse, tags=["root"])
async def root() -> RootResponse:
    """
    Root endpoint with service information.

    Returns:
        RootResponse with service details
    """
    return RootResponse(
        service="enterprise_core_utils",
        version="1.0.0",
        message="Enterprise Core Utils API - Stateless utility functions",
    )