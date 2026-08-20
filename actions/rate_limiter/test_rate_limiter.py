import pytest
import asyncio
from fastapi.testclient import TestClient
from actions.rate_limiter.main import app, limiter
from actions.rate_limiter.rate_limiter import RateLimiter
from actions.rate_limiter.schemas import RateLimitConfig

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_limiter_state():
    limiter.requests.clear()

def test_sliding_window_rate_limiter_logic():
    l = RateLimiter(RateLimitConfig(max_requests=2, window_seconds=0.2))
    
    # Prvi 2 zahtevi dovoljeni
    ok1, rem1, _ = l.is_allowed("client_a")
    assert ok1 is True
    assert rem1 == 1

    ok2, rem2, _ = l.is_allowed("client_a")
    assert ok2 is True
    assert rem2 == 0

    # 3. zahteva blokirana
    ok3, rem3, reset3 = l.is_allowed("client_a")
    assert ok3 is False
    assert rem3 == 0
    assert reset3 > 0

    # Po preteku okna ponovno dovoljeno
    asyncio.run(asyncio.sleep(0.25))
    ok4, rem4, _ = l.is_allowed("client_a")
    assert ok4 is True

def test_fastapi_rate_limiter_endpoint():
    key = "192.168.1.100"

    # Max 3 zahteve dovoljene
    for i in range(3):
        res = client.post("/check", json={"key": key})
        assert res.status_code == 200
        assert res.json()["allowed"] is True

    # 4. zahteva mora vrniti HTTP 429
    res_blocked = client.post("/check", json={"key": key})
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"] == "RATE_LIMIT_EXCEEDED"
