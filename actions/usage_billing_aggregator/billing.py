"""usage_billing_aggregator — jedro domenske logike: usage metering + obračun.

Kot predlaga arhitekturna revizija (2026): ``rate_limiter`` meri porabo,
ni pa obračuna, kvotnega preverjanja in agregacije po najemnikih (tenantih).
Ta modul doda:
  - tarifne pakete (Metered / Tiered / Quota),
  - visoko-prepustne števce porabe (per tenant + metrika),
  - dnevne/urne agregate,
  - kvotno preverjanje + auto-alert ob prekoračitvi,
  - obračunski summary (eksport v report_builder).

Vse je čisto, v spominu in deterministično (brez omrežja / baz).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

TariffKind = Literal["metered", "tiered", "quota"]


@dataclass
class TariffPackage:
    """Cenovni paket za najemnika."""

    name: str
    kind: TariffKind
    unit_price: float = 0.0
    # Tiered: meje + cene na tier (npr. [(100, 0.01), (None, 0.005)]).
    tier_limits: List[float] = field(default_factory=list)
    tier_prices: List[float] = field(default_factory=list)
    # Quota: dovoljena poraba na cikel + mesečna naročnina.
    quota_limit: float = 0.0
    monthly_fee: float = 0.0


@dataclass
class UsageRecord:
    """Eden zapis porabe."""

    tenant: str
    metric: str
    units: float
    timestamp: float


@dataclass
class UsageAlert:
    """Auto-alert ob prekoračeni kvoti."""

    tenant: str
    metric: str
    units: float
    limit: float
    message: str


class UsageBillingAggregator:
    """Agregacija porabe, kvote in obračun po najemnikih."""

    def __init__(self, clock: Optional[Any] = None):
        self._clock = clock or time.time
        self.tariffs: Dict[str, TariffPackage] = {}
        self.records: List[UsageRecord] = []
        self._counters: Dict[tuple, float] = {}   # (tenant, metric) → units
        self.alerts: List[UsageAlert] = []

    # ── Tarife ──────────────────────────────────────────────────────────────
    def register_tariff(self, tenant: str, package: TariffPackage) -> TariffPackage:
        self.tariffs[tenant] = package
        return package

    def get_tariff(self, tenant: str) -> Optional[TariffPackage]:
        return self.tariffs.get(tenant)

    # ── Poraba ──────────────────────────────────────────────────────────────
    def record_usage(self, tenant: str, metric: str, units: float) -> UsageRecord:
        """Beleži porabo; poveča števec in ob prekoračitvi kvote javi alert."""
        record = UsageRecord(tenant=tenant, metric=metric, units=units, timestamp=self._clock())
        self.records.append(record)
        key = (tenant, metric)
        self._counters[key] = self._counters.get(key, 0.0) + units
        self._check_quota(tenant, metric)
        return record

    def get_usage(self, tenant: str, metric: str) -> float:
        return self._counters.get((tenant, metric), 0.0)

    def usage_by_window(self, tenant: str, metric: str, window_seconds: float) -> float:
        """Agregacija porabe v zadnjem časovnem oknu."""
        cutoff = self._clock() - window_seconds
        return sum(
            r.units for r in self.records
            if r.tenant == tenant and r.metric == metric and r.timestamp >= cutoff
        )

    # ── Kvote + alerti ──────────────────────────────────────────────────────
    def _check_quota(self, tenant: str, metric: str) -> None:
        tariff = self.tariffs.get(tenant)
        if tariff is None or tariff.kind != "quota" or tariff.quota_limit <= 0:
            return
        units = self.get_usage(tenant, metric)
        if units >= tariff.quota_limit:
            self.alerts.append(
                UsageAlert(
                    tenant=tenant, metric=metric, units=units,
                    limit=tariff.quota_limit,
                    message=f"quota exceeded: {units:.0f} >= {tariff.quota_limit:.0f}",
                )
            )

    def quota_status(self, tenant: str, metric: str) -> Dict[str, Any]:
        tariff = self.tariffs.get(tenant)
        units = self.get_usage(tenant, metric)
        if tariff is None or tariff.kind != "quota":
            return {"tenant": tenant, "metric": metric, "enforced": False, "units": units}
        return {
            "tenant": tenant, "metric": metric, "enforced": True,
            "units": units, "limit": tariff.quota_limit,
            "exceeded": units >= tariff.quota_limit,
            "remaining": max(0.0, tariff.quota_limit - units),
        }

    # ── Obračun ─────────────────────────────────────────────────────────────
    def billing_summary(self, tenant: str) -> Dict[str, Any]:
        """Izračunaj strošek porabe po tarifi (metered/tiered/quota)."""
        tariff = self.tariffs.get(tenant)
        if tariff is None:
            return {"tenant": tenant, "tariff": None, "cost": 0.0, "details": {}}
        details: Dict[str, float] = {}
        total_cost = 0.0
        for (t, metric), units in self._counters.items():
            if t != tenant:
                continue
            cost = self._cost(tariff, units)
            details[metric] = cost
            total_cost += cost
        return {
            "tenant": tenant,
            "tariff": tariff.name,
            "kind": tariff.kind,
            "cost": round(total_cost, 4),
            "details": details,
        }

    @staticmethod
    def _cost(tariff: TariffPackage, units: float) -> float:
        if tariff.kind == "metered":
            return units * tariff.unit_price
        if tariff.kind == "tiered":
            remaining = units
            cost = 0.0
            for i, limit in enumerate(tariff.tier_limits):
                price = tariff.tier_prices[i] if i < len(tariff.tier_prices) else tariff.unit_price
                if limit is None:
                    cost += remaining * price
                    break
                tier_units = min(remaining, limit)
                cost += tier_units * price
                remaining -= tier_units
                if remaining <= 0:
                    break
            return cost
        if tariff.kind == "quota":
            over = max(0.0, units - tariff.quota_limit)
            return tariff.monthly_fee + over * tariff.unit_price
        return 0.0


__all__ = ["TariffPackage", "UsageRecord", "UsageAlert", "UsageBillingAggregator"]
