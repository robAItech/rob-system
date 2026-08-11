import httpx
from typing import Dict, Optional, Tuple, Any
from actions.enterprise_api_gateway.schemas import RouteConfig, GatewayRequestPayload, GatewayResponse

class GatewayMiddlewarePipeline:
    @staticmethod
    def process_auth(headers: Dict[str, str], route: RouteConfig) -> Tuple[bool, Optional[str]]:
        if not route.require_auth:
            return True, None
        auth_header = headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return False, "Missing or invalid Authorization header"
        return True, None

    @staticmethod
    def process_rate_limit(client_ip: str, route: RouteConfig) -> Tuple[bool, Optional[str]]:
        if route.rate_limit_max <= 0:
            return False, "Rate limit exceeded"
        return True, None

class EnterpriseApiGateway:
    def __init__(self):
        self.routes: Dict[str, RouteConfig] = {}
        self.timeout = 5.0

    def register_route(self, route: RouteConfig) -> None:
        self.routes[route.id] = route

    def match_route(self, path: str) -> Optional[RouteConfig]:
        matched_route = None
        longest_match = 0
        for route in self.routes.values():
            if path.startswith(route.path_prefix) and len(route.path_prefix) > longest_match:
                matched_route = route
                longest_match = len(route.path_prefix)
                
        return matched_route

    async def forward_request(self, payload: GatewayRequestPayload, client_ip: str = "127.0.0.1") -> GatewayResponse:
        route = self.match_route(payload.path)
        if not route:
            return GatewayResponse(status_code=404, headers={}, data={"error": "ROUTE_NOT_FOUND"})

        auth_ok, auth_err = GatewayMiddlewarePipeline.process_auth(payload.headers, route)
        if not auth_ok:
            return GatewayResponse(status_code=401, headers={}, data={"error": "UNAUTHORIZED", "detail": auth_err})

        rl_ok, rl_err = GatewayMiddlewarePipeline.process_rate_limit(client_ip, route)
        if not rl_ok:
            return GatewayResponse(status_code=429, headers={}, data={"error": "TOO_MANY_REQUESTS", "detail": rl_err})

        relative_path = payload.path[len(route.path_prefix):]
        if not relative_path.startswith("/"):
            relative_path = "/" + relative_path
            
        target_url = f"{route.upstream_url.rstrip('/')}{relative_path}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=payload.method,
                    url=target_url,
                    headers={k: v for k, v in payload.headers.items() if k.lower() != "host"},
                    json=payload.body if payload.body else None
                )
                try:
                    resp_data = response.json()
                except Exception:
                    resp_data = response.text

                return GatewayResponse(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    data=resp_data
                )
        except httpx.TimeoutException:
            return GatewayResponse(status_code=504, headers={}, data={"error": "GATEWAY_TIMEOUT"})
        except httpx.RequestError as e:
            return GatewayResponse(status_code=502, headers={}, data={"error": "BAD_GATEWAY", "detail": str(e)})
