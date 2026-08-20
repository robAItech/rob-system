import pytest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from actions.api_gateway.main import app, dispatcher
from actions.api_gateway.webhooks import WebhookDispatcher
from actions.api_gateway.schemas import WebhookEndpoint, WebhookEvent, WebhookStatus

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_dispatcher():
    dispatcher.endpoints.clear()
    dispatcher.results.clear()

@pytest.mark.asyncio
async def test_webhook_successful_delivery():
    d = WebhookDispatcher()
    ep = WebhookEndpoint(id="ep_1", url="http://mock.test/hook", secret="super_secret_key_123", max_retries=1)
    d.register_endpoint(ep)
    
    event = WebhookEvent(event_id="evt_1", event_type="user.created", payload={"user": "rob"})

    class MockResponse:
        status_code = 200

    # Mocking httpx.AsyncClient.post to simulate a successful 200 OK response
    with patch("httpx.AsyncClient.post", return_value=MockResponse()) as mock_post:
        result = await d.dispatch("ep_1", event)
        
        assert result is not None
        assert result.status == WebhookStatus.DELIVERED
        assert len(result.attempts) == 1
        assert result.attempts[0].success is True
        
        # Verify HMAC signature header was sent
        call_kwargs = mock_post.call_args.kwargs
        assert "X-Webhook-Signature" in call_kwargs["headers"]
        assert call_kwargs["headers"]["X-Webhook-Signature"].startswith("v1=")

@pytest.mark.asyncio
async def test_webhook_retry_logic_and_failure():
    d = WebhookDispatcher()
    ep = WebhookEndpoint(id="ep_2", url="http://mock.test/fail", secret="super_secret_key_123", max_retries=1)
    d.register_endpoint(ep)
    
    event = WebhookEvent(event_id="evt_2", event_type="payment.failed")

    class MockErrorResponse:
        status_code = 500

    # We mock sleep to avoid waiting during tests
    with patch("httpx.AsyncClient.post", return_value=MockErrorResponse()), patch("asyncio.sleep", return_value=None):
        result = await d.dispatch("ep_2", event)
        
        assert result is not None
        assert result.status == WebhookStatus.FAILED
        assert len(result.attempts) == 2 # Initial try + 1 retry
        assert result.attempts[0].success is False
        assert result.attempts[1].success is False

def test_fastapi_webhook_endpoints():
    # 1. Register endpoint
    res_ep = client.post("/endpoints", json={
        "id": "target_a",
        "url": "https://api.example.com/webhook",
        "secret": "my_secure_signing_secret_12345",
        "max_retries": 2
    })
    assert res_ep.status_code == 201

    # 2. Dispatch event (Background Task)
    res_dispatch = client.post("/dispatch/target_a", json={
        "event_id": "test_evt_001",
        "event_type": "account.updated",
        "payload": {"status": "active"}
    })
    assert res_dispatch.status_code == 200
    assert res_dispatch.json()["status"] == "DISPATCH_QUEUED"
    
    # 3. Trigger 404 for non-existent endpoint
    res_dispatch_404 = client.post("/dispatch/invalid_target", json={
        "event_id": "test_evt_002",
        "event_type": "account.updated"
    })
    assert res_dispatch_404.status_code == 404
