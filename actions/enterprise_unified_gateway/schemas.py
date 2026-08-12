"""
Pydantic schemas for the Enterprise Unified Gateway module.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RoutePayload(BaseModel):
    """
    Payload for routing requests to virtual microservices.
    """

    service_name: str = Field(
        ..., description="Name of the target virtual microservice"
    )
    method: str = Field(
        default="GET", description="HTTP method for the routed request"
    )
    path: str = Field(
        default="/", description="Path within the target service"
    )
    headers: Optional[Dict[str, str]] = Field(
        default_factory=dict, description="Headers to forward to the target service"
    )
    body: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Request body to forward"
    )
    query_params: Optional[Dict[str, str]] = Field(
        default_factory=dict, description="Query parameters to forward"
    )


class RouteResponse(BaseModel):
    """
    Response model for routed requests.
    """

    success: bool = Field(..., description="Whether the routing was successful")
    service_name: str = Field(..., description="Name of the target service")
    status_code: int = Field(..., description="HTTP status code from the target service")
    data: Optional[Dict[str, Any]] = Field(
        default=None, description="Response data from the target service"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if routing failed"
    )