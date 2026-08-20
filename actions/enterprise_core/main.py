"""
Enterprise Core — unified FastAPI application.

Združuje nekdanja enterprise_core_contracts + enterprise_core_utils v en
jedrni modul: skupni data contracts (DTO-ji) in utility funkcije.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from actions.enterprise_core.schemas import HealthResponse

app = FastAPI(
    title="Enterprise Core",
    description="Core data contracts, DTOs and utility functions for the enterprise system",
    version="1.0.0",
)

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
        "service": "enterprise_core",
        "version": "1.0.0",
        "status": "running",
    }
