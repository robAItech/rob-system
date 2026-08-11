import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from actions.enterprise_api_gateway.main import app, gateway
from actions.enterprise_api_gateway.schemas import RouteConfig, GatewayRequestPayload

client = TestClient(app)

@pytest.fixture(autouse=True)
def ensure_routes():
    gateway.routes.clear()
    gateway.register_route(RouteConfig(id="test_open", path_prefix="/open", upstream_url="http://mock.open"))
    gateway.register_route(RouteConfig(id="test_secure", path_prefix="/secure", upstream_url="http://mock.secure", require_auth=True))
    gateway.register_route(RouteConfig(id="test_limited", path_prefix="/limited", upstream_url="http://mock.limited", rate_limit_max=0))

@pytest.mark.asyncio
async def test_gateway_route_matching_and_middleware():
    # 1. 404 Route Not Found
    req_404 = GatewayRequestPayload(path="/unknown/path")
    res_404 = await gateway.forward_request(req_404)
    assert res_404.status_code == 404

    # 2. 401 Unauthorized (Missing Header)
    req_401 = GatewayRequestPayload(path="/secure/data")
    res_401 = await gateway.forward_request(req_401)
    assert res_401.status_code == 401

    # 3. 429 Rate Limit Exceeded
    req_429 = GatewayRequestPayload(path="/limited/resource")
    res_429 = await gateway.forward_request(req_429)
    assert res_429.status_code == 429

@pytest.mark.asyncio
async def test_gateway_successful_proxy():
    req_ok = GatewayRequestPayload(
        method="GET",
        path="/open/status",
        headers={"host": "localhost"}
    )
    
    class MockHttpxResponse:
        status_code = 200
        headers = {"x-mock": "true"}
        def json(self):
            return {"status": "upstream_ok"}
            
    with patch("httpx.AsyncClient.request", return_value=MockHttpxResponse()) as mock_req:
        res = await gateway.forward_request(req_ok)
        assert res.status_code == 200
        assert res.data["status"] == "upstream_ok"
        
        # Preveri, če je prefix pravilno odrezan
        call_kwargs = mock_req.call_args.kwargs
        assert call_kwargs["url"] == "http://mock.open/status"

def test_fastapi_gateway_catch_all():
    # Test Route Not Found via FastAPI
    res_404 = client.get("/non_existent_route")
    assert res_404.status_code == 404
    assert res_404.json()["error"] == "ROUTE_NOT_FOUND"

    # Test Secure Route Rejection
    res_401 = client.post("/secure/update", json={"data": 123})
    assert res_401.status_code == 401
    assert res_401.json()["error"] == "UNAUTHORIZED"
