from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from actions.enterprise_api_gateway.schemas import RouteConfig, GatewayRequestPayload
from actions.enterprise_api_gateway.enterprise_api_gateway import EnterpriseApiGateway

app = FastAPI(title="Rob AI Studio - Enterprise API Gateway")
gateway = EnterpriseApiGateway()

ROUTES = [
    ("auth_service", "/api/auth", "http://127.0.0.1:8001", False),
    ("audit_service", "/api/audit", "http://127.0.0.1:8002", True),
    ("event_bus", "/api/events", "http://127.0.0.1:8003", True),
    ("task_queue", "/api/tasks", "http://127.0.0.1:8004", True),
    ("cache_layer", "/api/cache", "http://127.0.0.1:8005", True),
    ("rate_limiter", "/api/limit", "http://127.0.0.1:8006", False),
    ("circuit_breaker", "/api/breaker", "http://127.0.0.1:8007", True),
    ("webhook_dispatcher", "/api/webhooks", "http://127.0.0.1:8008", True),
    ("feature_flag", "/api/flags", "http://127.0.0.1:8009", False),
    ("metrics", "/api/metrics", "http://127.0.0.1:9090", False),
]

for r_id, prefix, url, req_auth in ROUTES:
    gateway.register_route(RouteConfig(id=r_id, path_prefix=prefix, upstream_url=url, require_auth=req_auth))

@app.get("/gateway/health")
async def health():
    return {"status": "ok"}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(path: str, request: Request):
    headers = dict(request.headers)
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.json()
        except Exception:
            body = {}

    client_ip = request.client.host if request.client else "127.0.0.1"
    gw_payload = GatewayRequestPayload(method=request.method, path=f"/{path}", headers=headers, body=body)
    gw_response = await gateway.forward_request(gw_payload, client_ip)
    
    return JSONResponse(status_code=gw_response.status_code, content=gw_response.data)
