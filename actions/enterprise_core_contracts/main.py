"""
Enterprise Core Contracts - FastAPI Application.

This module provides a minimal FastAPI application with health check endpoint.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from actions.enterprise_core_contracts.schemas import HealthResponse

app = FastAPI(
    title="Enterprise Core Contracts",
    description="Core data contracts and DTOs for the enterprise system",
    version="1.0.0",
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    
    Returns:
        HealthResponse: Health check response
    """
    return HealthResponse(
        status="ok",
        version="1.0.0",
    )


@app.get("/", tags=["root"])
async def root() -> dict:
    """
    Root endpoint.
    
    Returns:
        dict: Service information
    """
    return {
        "service": "enterprise_core_contracts",
        "version": "1.0.0",
        "status": "running",
    }