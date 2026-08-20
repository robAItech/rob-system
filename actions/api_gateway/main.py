"""
Enterprise API Gateway — unified FastAPI application.

Združuje nekdanja ``enterprise_unified_gateway`` (usmerjanje zahtevkov na
mikrostoritve) in ``enterprise_webhook_dispatcher`` (razpošiljanje webhookov)
v en vhodni point z enotnim middleware pipeline-om.
"""

from typing import Any, Dict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from actions.api_gateway.gateway import GatewayRouter
from actions.api_gateway.schemas import (
    DeliveryResult,
    RoutePayload,
    RouteResponse,
    WebhookEndpoint,
    WebhookEvent,
)
from actions.api_gateway.webhooks import EnterpriseWebhookDispatcher

app = FastAPI(
    title="Enterprise API Gateway",
    description="Unified gateway for routing requests to microservices and dispatching webhooks",
    version="1.0.0",
)

gateway_router = GatewayRouter()
dispatcher = EnterpriseWebhookDispatcher()


# ── Gateway: usmerjanje zahtevkov ────────────────────────────────────────────
@app.get("/health", response_model=Dict[str, str])
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Dictionary with health status.
    """
    return {"status": "healthy", "service": "api_gateway"}


@app.post("/route/{service_name}", response_model=RouteResponse)
async def route_request(service_name: str, request: Request) -> RouteResponse:
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
        body = await request.json() if await request.body() else {}
        payload = RoutePayload(
            service_name=service_name,
            method=request.method,
            path=str(request.url.path),
            headers=dict(request.headers),
            body=body,
            query_params=dict(request.query_params),
        )
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


@app.get("/services", response_model=Dict[str, list])
async def list_services() -> Dict[str, list]:
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


# ── Webhooks: razpošiljanje ──────────────────────────────────────────────────
@app.post("/endpoints", status_code=status.HTTP_201_CREATED)
async def create_endpoint(endpoint: WebhookEndpoint):
    """
    Register a webhook endpoint.
    """
    dispatcher.register_endpoint(endpoint)
    return {"status": "REGISTERED", "endpoint_id": endpoint.id}


@app.post("/dispatch/{endpoint_id}", response_model=Dict[str, str])
async def dispatch_webhook(
    endpoint_id: str,
    event: WebhookEvent,
    background_tasks: BackgroundTasks,
):
    """
    Dispatch a webhook event to a registered endpoint (async, background).
    """
    if endpoint_id not in dispatcher.endpoints:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    background_tasks.add_task(dispatcher.dispatch, endpoint_id, event)
    return {"status": "DISPATCH_QUEUED", "event_id": event.event_id}


@app.get("/results/{event_id}/{endpoint_id}", response_model=DeliveryResult)
async def get_delivery_result(event_id: str, endpoint_id: str):
    """
    Get the delivery result for a webhook event.
    """
    key = f"{event_id}_{endpoint_id}"
    result = dispatcher.results.get(key)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found or pending")
    return result
