"""Testi za actions runtime app (korak 5) — brez omrežja, brez uvicorn.

Preveri: mount vseh 21 modulov (18 originalnih + 3 nova enterprise: webhook_dispatcher,
api_version_manager, secret_rotation), allowlist health, auth (401/veljaven ključ),
rate-limit (429), audit na deljenem busu, toleranca na broken modul.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.actions_runtime import RuntimeConfig, RuntimeServices, build_runtime_app, load_module_app
from actions.rate_limiter.schemas import RateLimitConfig

ALL_NAMES = {
    "api_gateway", "audit_trail", "auth_vault", "cache_layer", "circuit_breaker",
    "contract_schema_engine", "currency_converter", "deployment_manager", "event_bus",
    "feature_flag", "mailer", "nexus_command_deck", "observability_metrics",
    "rate_limiter", "rsi_engine", "saga_orchestrator", "task_queue", "warehouse_inventory",
    "webhook_dispatcher", "api_version_manager", "secret_rotation",
}


def _admin_key(client) -> str:
    issued = client.post("/api/runtime/keys/issue",
                         json={"client_id": "test", "role": "ADMIN", "ttl_days": 1}).json()
    return issued["api_key"]


def test_mounts_all_21():
    app = build_runtime_app(modules=sorted(ALL_NAMES))
    with TestClient(app) as client:
        mods = client.get("/api/runtime/modules").json()
    mounted = {m["name"] for m in mods if m["mounted"]}
    assert mounted == ALL_NAMES
    assert len(mounted) == 21


def test_health_endpoints_public():
    app = build_runtime_app(modules=sorted(ALL_NAMES))
    with TestClient(app) as client:
        for name in ("api_gateway", "contract_schema_engine", "observability_metrics",
                     "saga_orchestrator", "webhook_dispatcher", "api_version_manager",
                     "secret_rotation"):
            r = client.get(f"/api/{name}/health")
            assert r.status_code == 200, f"{name}: {r.status_code}"


def test_no_key_401():
    app = build_runtime_app(modules=sorted(ALL_NAMES))
    with TestClient(app) as client:
        r = client.get("/api/event_bus/topics")
    assert r.status_code == 401


def test_issue_key_flow_and_valid_key_ok():
    app = build_runtime_app(modules=sorted(ALL_NAMES))
    with TestClient(app) as client:
        key = _admin_key(client)
        r = client.get("/api/event_bus/topics", headers={"X-API-Key": key})
    assert r.status_code == 200


def test_rate_limit_429():
    app = build_runtime_app(
        modules=sorted(ALL_NAMES),
        config=RuntimeConfig(rate_limit_config=RateLimitConfig(max_requests=1, window_seconds=60)),
    )
    with TestClient(app) as client:
        key = _admin_key(client)
        first = client.get("/api/event_bus/topics", headers={"X-API-Key": key})
        second = client.get("/api/event_bus/topics", headers={"X-API-Key": key})
    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers.get("Retry-After")


def test_audit_publishes_on_shared_bus():
    app = build_runtime_app(modules=sorted(ALL_NAMES))
    with TestClient(app) as client:
        key = _admin_key(client)
        client.get("/api/event_bus/topics", headers={"X-API-Key": key})
    services: RuntimeServices = app.state.runtime_services
    assert len(services.bus.get_topic_messages("requests")) >= 1
    assert len(services.audit.chain) >= 1


def test_load_module_app_missing_returns_none():
    assert load_module_app("definitely_not_a_module") is None


def test_build_tolerates_broken_module(monkeypatch):
    from core import actions_runtime

    def broken_load(name):
        if name == "event_bus":
            return None
        return __import__(f"actions.{name}.main", fromlist=["app"])

    monkeypatch.setattr(actions_runtime, "_load_module", broken_load)
    app = build_runtime_app(modules=["auth_vault", "event_bus"])
    services: RuntimeServices = app.state.runtime_services
    assert "auth_vault" in services.mounted
    assert "event_bus" in services.skipped
