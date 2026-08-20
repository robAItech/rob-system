import pytest
import asyncio
from fastapi.testclient import TestClient
from actions.circuit_breaker.main import app, breakers
from actions.circuit_breaker.circuit_breaker import EnterpriseCircuitBreaker
from actions.circuit_breaker.schemas import CircuitState, CircuitConfig

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_breakers():
    breakers.clear()

def test_circuit_breaker_logic():
    cb = EnterpriseCircuitBreaker("test_service", CircuitConfig(failure_threshold=2, recovery_timeout=0.1, half_open_success_threshold=2))
    assert cb.state == CircuitState.CLOSED
    cb.on_failure()
    cb.on_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False
    asyncio.run(asyncio.sleep(0.15))
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN
    cb.on_success()
    cb.on_success()
    assert cb.state == CircuitState.CLOSED

def test_fastapi_api():
    service = "payment"
    res = client.post("/execute", json={"service_name": service, "should_fail": False})
    assert res.status_code == 200

    for _ in range(3):
        client.post("/execute", json={"service_name": service, "should_fail": True})

    res_blocked = client.post("/execute", json={"service_name": service, "should_fail": False})
    assert res_blocked.status_code == 429
    assert res_blocked.json()["error"] == "CIRCUIT_OPEN"
