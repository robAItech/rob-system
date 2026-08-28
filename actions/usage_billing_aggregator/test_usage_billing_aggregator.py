"""Pytest test suite za actions/usage_billing_aggregator.

Deterministično (fiktivna ura). Preveri: meter/tiered/quota tarife, agregacijo
porabe (skupno + okno), kvotne alerte, obračun in FastAPI plast.
"""

import pytest
from fastapi.testclient import TestClient

from actions.usage_billing_aggregator.billing import TariffPackage, UsageBillingAggregator
from actions.usage_billing_aggregator.main import app, aggregator


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture(autouse=True)
def _fresh_aggregator():
    aggregator.tariffs.clear()
    aggregator.records.clear()
    aggregator._counters.clear()
    aggregator.alerts.clear()
    yield


# ── Metered ─────────────────────────────────────────────────────────────────
def test_metered_billing():
    agg = UsageBillingAggregator()
    agg.register_tariff("acme", TariffPackage(name="metered", kind="metered", unit_price=0.01))
    agg.record_usage("acme", "api_calls", 100)
    agg.record_usage("acme", "api_calls", 50)
    assert agg.get_usage("acme", "api_calls") == 150
    summary = agg.billing_summary("acme")
    assert summary["kind"] == "metered"
    assert summary["cost"] == 1.5  # 150 * 0.01


# ── Tiered ──────────────────────────────────────────────────────────────────
def test_tiered_billing():
    agg = UsageBillingAggregator()
    agg.register_tariff(
        "acme",
        TariffPackage(name="tiered", kind="tiered", tier_limits=[100, None], tier_prices=[0.01, 0.005]),
    )
    agg.record_usage("acme", "calls", 250)
    summary = agg.billing_summary("acme")
    # 100 * 0.01 + 150 * 0.005 = 1.0 + 0.75 = 1.75
    assert summary["cost"] == 1.75


# ── Quota + alert ───────────────────────────────────────────────────────────
def test_quota_alert_on_exceed():
    agg = UsageBillingAggregator()
    agg.register_tariff(
        "acme", TariffPackage(name="quota", kind="quota", quota_limit=100, monthly_fee=10, unit_price=0.02),
    )
    agg.record_usage("acme", "tokens", 60)
    assert agg.alerts == []  # pod kvoto
    agg.record_usage("acme", "tokens", 50)  # skupaj 110 >= 100
    assert len(agg.alerts) == 1
    assert "exceeded" in agg.alerts[0].message

    status = agg.quota_status("acme", "tokens")
    assert status["exceeded"] is True
    assert status["remaining"] == 0.0

    # Obračun: naročnina + 10 nad kvoto * 0.02
    summary = agg.billing_summary("acme")
    assert summary["cost"] == pytest.approx(10.2)


# ── Okno (agregacija) ───────────────────────────────────────────────────────
def test_usage_by_window():
    clock = FakeClock(1000.0)
    agg = UsageBillingAggregator(clock=clock)
    agg.register_tariff("acme", TariffPackage(name="m", kind="metered"))
    agg.record_usage("acme", "calls", 10)
    clock.advance(100)
    agg.record_usage("acme", "calls", 20)
    # V zadnjih 50 s je le 20.
    assert agg.usage_by_window("acme", "calls", 50) == 20
    assert agg.get_usage("acme", "calls") == 30


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_flow():
    client = TestClient(app)
    r = client.post("/tariffs", json={"tenant": "acme", "name": "metered", "kind": "metered", "unit_price": 0.01})
    assert r.status_code == 200

    r2 = client.post("/usage", json={"tenant": "acme", "metric": "api_calls", "units": 200})
    assert r2.status_code == 200
    assert r2.json()["total"] == 200

    r3 = client.get("/billing/acme")
    assert r3.json()["cost"] == 2.0

    assert client.get("/health").json()["status"] == "UP"
