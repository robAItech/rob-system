import pytest
from fastapi.testclient import TestClient
from actions.observability_metrics.main import app, registry

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_registry():
    registry.http_metrics.clear()
    registry.counters.clear()

def test_metrics_middleware_and_snapshot():
    # 1. Simulacija zahtev skozi middleware
    res_health = client.get("/health")
    assert res_health.status_code == 200
    
    res_404 = client.get("/non_existent_route")
    assert res_404.status_code == 404

    # 2. Preverjanje snapshot JSONa
    res_snap = client.get("/snapshot")
    assert res_snap.status_code == 200
    data = res_snap.json()
    
    # 2 zabeleženi zahtevi (health in 404). 
    # Tretja zahteva (sam /snapshot) se v middleware zabeleži šele PO tem, ko se endpoint izvede.
    assert data["total_requests"] == 2
    assert data["error_count"] == 1
    assert data["avg_latency_ms"] >= 0.0

def test_prometheus_export_format():
    # Pošljemo testno zahtevo
    client.get("/health")
    
    # Preverimo Prometheus plain-text format
    res_prom = client.get("/metrics")
    assert res_prom.status_code == 200
    text = res_prom.text
    
    assert "# HELP http_requests_total" in text
    assert "http_requests_total{method=\"GET\",endpoint=\"/health\",status=\"200\"} 1" in text
    assert "http_request_duration_seconds_sum" in text
