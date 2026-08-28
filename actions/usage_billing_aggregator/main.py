"""usage_billing_aggregator — FastAPI aplikacija (API plast).

Expose: tarife, beleženje porabe, agregati, kvote, obračun + health.
Exporta ``app`` — v runtime pod ``/api/usage_billing_aggregator/*``.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from actions.usage_billing_aggregator.billing import TariffPackage, UsageBillingAggregator
from actions.usage_billing_aggregator.schemas import (
    TariffRegisterRequest,
    UsageRecordRequest,
)

app = FastAPI(title="Rob AI Studio - Usage Billing Aggregator", version="1.0.0")
aggregator = UsageBillingAggregator()


@app.post("/tariffs")
async def register_tariff(body: TariffRegisterRequest) -> JSONResponse:
    """Registriraj tarifni paket za najemnika."""
    package = TariffPackage(
        name=body.name,
        kind=body.kind,
        unit_price=body.unit_price,
        tier_limits=[l for l in body.tier_limits],
        tier_prices=list(body.tier_prices),
        quota_limit=body.quota_limit,
        monthly_fee=body.monthly_fee,
    )
    aggregator.register_tariff(body.tenant, package)
    return JSONResponse({"tenant": body.tenant, "tariff": package.name, "kind": package.kind})


@app.post("/usage")
async def record_usage(body: UsageRecordRequest) -> JSONResponse:
    """Beleži porabo; ob prekoračitvi kvote vrže alert v odgovor."""
    record = aggregator.record_usage(body.tenant, body.metric, body.units)
    alerts = [a for a in aggregator.alerts
              if a.tenant == body.tenant and a.metric == body.metric]
    return JSONResponse({"recorded": record.units, "total": aggregator.get_usage(body.tenant, body.metric),
                         "alerts": [a.message for a in alerts]})


@app.get("/usage/{tenant}/{metric}")
async def usage(tenant: str, metric: str, window_seconds: float = 0.0) -> JSONResponse:
    """Skupna poraba (ali v časovnem oknu, če je window_seconds > 0)."""
    total = aggregator.get_usage(tenant, metric)
    if window_seconds and window_seconds > 0:
        windowed = aggregator.usage_by_window(tenant, metric, window_seconds)
        return JSONResponse({"tenant": tenant, "metric": metric, "total": total, "window_seconds": window_seconds, "window_usage": windowed})
    return JSONResponse({"tenant": tenant, "metric": metric, "total": total})


@app.get("/quota/{tenant}/{metric}")
async def quota(tenant: str, metric: str) -> JSONResponse:
    """Kvotno stanje za najemnika + metriko."""
    return JSONResponse(aggregator.quota_status(tenant, metric))


@app.get("/billing/{tenant}")
async def billing(tenant: str) -> JSONResponse:
    """Obračunski summary (metered/tiered/quota)."""
    summary = aggregator.billing_summary(tenant)
    if summary["tariff"] is None:
        raise HTTPException(status_code=404, detail="no tariff for tenant")
    return JSONResponse(summary)


@app.get("/alerts")
async def alerts() -> JSONResponse:
    """Vsi kvotni alerti."""
    return JSONResponse(
        [{"tenant": a.tenant, "metric": a.metric, "units": a.units, "limit": a.limit, "message": a.message}
         for a in aggregator.alerts]
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return {"status": "UP", "tenants": sorted(aggregator.tariffs.keys())}
