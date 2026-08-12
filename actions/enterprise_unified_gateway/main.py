"""
FastAPI application for the Enterprise Unified Gateway.
"""

from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from actions.enterprise_unified_gateway.enterprise_unified_gateway import GatewayRouter
from actions.enterprise_unified_gateway.schemas import RoutePayload, RouteResponse

app = FastAPI(
    title="Enterprise Unified Gateway",
    description="Unified gateway for routing requests to virtual microservices",
    version="1.0.0",
)

# Initialize the gateway router
gateway_router = GatewayRouter()


@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Dictionary with health status.
    """
    return {"status": "healthy", "service": "enterprise_unified_gateway"}


@app.post("/route/{service_name}", response_model=RouteResponse)
async def route_request(
    service_name: str,
    request: Request,
) -> RouteResponse:
    """
    Dynamic endpoint to route requests to virtual microservices.

    Args:
        service_name: Name of the target virtual microservice.
        request: The incoming HTTP request.

    Returns:
        RouteResponse with the routing result.

    Raises:
        HTTPException: If the service is not found or request processing fails.
    """
    try:
        # Parse the request body
        body = await request.json() if await request.body() else {}

        # Build the RoutePayload
        payload = RoutePayload(
            service_name=service_name,
            method=request.method,
            path=str(request.url.path),
            headers=dict(request.headers),
            body=body,
            query_params=dict(request.query_params),
        )

        # Route the request
        response = gateway_router.route(payload)

        if not response.success:
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=response.error)
            raise HTTPException(status_code=response.status_code, detail=response.error)

        return response

    except HTTPException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(exc)}") from exc


@app.get("/services", response_model=Dict[str, list[str]])
async def list_services() -> Dict[str, list[str]]:
    """
    List all registered virtual microservices.

    Returns:
        Dictionary with list of registered services.
    """
    return {"services": gateway_router.get_registered_services()}


@app.post("/register/{service_name}")
async def register_service(service_name: str) -> JSONResponse:
    """
    Register a new virtual microservice (for testing/demo purposes).

    Args:
        service_name: Name of the service to register.

    Returns:
        JSON response confirming registration.
    """
    def default_handler(payload: RoutePayload) -> Dict[str, Any]:
        """Default handler for demo services."""
        return {
            "message": f"Service '{payload.service_name}' processed the request",
            "method": payload.method,
            "path": payload.path,
            "body": payload.body,
        }

    try:
        gateway_router.register_service(service_name, default_handler)
        return JSONResponse(
            status_code=200,
            content={"message": f"Service '{service_name}' registered successfully"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc