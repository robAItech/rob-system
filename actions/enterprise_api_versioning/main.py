"""
FastAPI application with version validation middleware.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

from actions.enterprise_api_versioning.enterprise_api_versioning import VersionManager
from actions.enterprise_api_versioning.schemas import HealthResponse, VersionInfo


# Initialize version manager
version_manager = VersionManager(
    current_version="1.0.0",
    supported_versions=["1.0.0", "1.1.0", "2.0.0"]
)


class VersionValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate Accept-Version header for all requests.
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and validate version header.
        
        Args:
            request: The incoming request
            call_next: The next middleware/route handler
            
        Returns:
            Response: Either 406 error or the actual response
        """
        # Skip version validation for health endpoint
        if request.url.path == "/health":
            return await call_next(request)
        
        # Get Accept-Version header
        version_header = request.headers.get("Accept-Version")
        
        # Validate version
        is_valid, error_message = version_manager.validate_version_header(version_header)
        
        if not is_valid:
            return JSONResponse(
                status_code=406,
                content={
                    "error": "Not Acceptable",
                    "message": error_message,
                    "supported_versions": version_manager.supported_versions
                }
            )
        
        # Add validated version to request state
        request.state.api_version = version_header
        
        # Process the request
        response = await call_next(request)
        return response


# Create FastAPI app
app = FastAPI(
    title="Enterprise API Versioning",
    description="API with version validation middleware",
    version="1.0.0"
)

# Add middleware
app.add_middleware(VersionValidationMiddleware)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns:
        HealthResponse: Health status and version info
    """
    return HealthResponse(
        status="ok",
        version=version_manager.current_version
    )


@app.get("/version", response_model=VersionInfo, tags=["version"])
async def get_version_info():
    """
    Get current version information.
    
    Returns:
        VersionInfo: Version details
    """
    info = version_manager.get_version_info()
    return VersionInfo(
        current_version=info["current_version"],
        supported_versions=info["supported_versions"],
        deprecated_versions=info["deprecated_versions"]
    )


@app.get("/protected", tags=["protected"])
async def protected_endpoint(request: Request):
    """
    Protected endpoint that requires valid version.
    
    Args:
        request: The request object
        
    Returns:
        dict: Success message with version
    """
    return {
        "message": "Access granted",
        "api_version": request.state.api_version
    }