from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional, List

class RouteConfig(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(..., min_length=1)
    path_prefix: str = Field(..., description="Prefix to match, e.g., /api/v1/users")
    upstream_url: str = Field(..., description="Target upstream service URL")
    require_auth: bool = Field(default=False)
    rate_limit_max: int = Field(default=100)
    use_circuit_breaker: bool = Field(default=True)

class GatewayRequestPayload(BaseModel):
    method: str = Field(default="GET")
    path: str = Field(...)
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Dict[str, Any]] = None

class GatewayResponse(BaseModel):
    status_code: int
    headers: Dict[str, str]
    data: Any
