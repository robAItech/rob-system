"""fleet_security — operator monitor (Phase 2, Skin A).

Pasivni telemetry + omrežne opazke → anomalija/egress detekcija → najdbe v
ISTI ``fs_findings`` tok (posture scoring + CRA + eskalacija ostanejo eno).

Detekcija (deterministično, brez LLM, brez omrežja):
- **telemetry:** z-score zadnjega vzorca vs. rolling baseline (populacijska
  varianca, ``actions.signal_calc.z_score``); ``|z| >= prag`` → finding
  (>= 5.0 high, sicer medium). Flat data → ``z=0.0`` → ni anomalije.
- **egress:** window-based first-seen dst (host/ip), ki ni v allowlist →
  ``unknown_egress`` (high); >= 5 različnih unknown dst v oknu →
  ``egress_anomaly`` (medium). Allowlist = domene/IP/CIDR (ipaddress idiom
  iz ``actions/governance_policy_enforcer``).

Vse najdbe gredo skozi ``store.upsert_findings`` z ``resolve_categories``
scopom — monitor resolve-a SAMO svoje kategorije in ne clobber-a posture.
"""

from __future__ import annotations

import sys
import time
from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit  # noqa: E402
from core.config import settings  # noqa: E402
from actions.signal_calc.z_score import z_score  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    NetworkObservation,
    PostureFinding,
    TelemetrySample,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

#: Egress detekcijsko okno (v sekundah) — "first-seen" je definiran znotraj okna.
EGRESS_WINDOW_SECONDS = 3600
#: Prag števila različnih unknown dst v oknu → egress_anomaly.
EGRESS_BURST_THRESHOLD = 5
#: |z| >= toliko → high severity (sicer medium nad pragom).
ANOMALY_HIGH_Z = 5.0
#: Kategorije, ki jih piše/resolve-a monitor (scope za resolve_categories).
MONITOR_CATEGORIES = frozenset({"telemetry_anomaly", "unknown_egress", "egress_anomaly"})


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ #
#  Ingest (pasivno; vsak zapis → audit)
# ------------------------------------------------------------------ #
def ingest_telemetry(
    store: FleetSecurityStore, sample: TelemetrySample, now: int | None = None
) -> dict:
    """Shrani telemetry vzorec + audit event. Vrne {"id", "device_id", "ts"}."""
    now = int(now) if now is not None else _now()
    ts = int(sample.ts) if sample.ts is not None else now
    row_id = store.append_telemetry(sample.device_id, ts, sample.source, sample.metrics)
    try:
        audit.record(
            event="fleet-security-telemetry",
            project=sample.device_id,
            status="ok",
            detail=f"ts={ts} metrics={sorted(sample.metrics)}",
        )
    except Exception:
        pass
    return {"id": row_id, "device_id": sample.device_id, "ts": ts}


def ingest_network_observation(
    store: FleetSecurityStore, obs: NetworkObservation, now: int | None = None
) -> dict:
    """Shrani omrežno opazko + audit event. Vrne {"id", "device_id", "ts", "dst"}."""
    now = int(now) if now is not None else _now()
    ts = int(obs.ts) if obs.ts is not None else now
    row_id = store.append_network_observation(
        obs.device_id, ts, obs.dst_host, obs.dst_ip, obs.dst_port, obs.proto
    )
    try:
        audit.record(
            event="fleet-security-network",
            project=obs.device_id,
            status="ok",
            detail=f"ts={ts} dst={obs.dst_host or obs.dst_ip}",
        )
    except Exception:
        pass
    return {
        "id": row_id,
        "device_id": obs.device_id,
        "ts": ts,
        "dst": obs.dst_host or obs.dst_ip,
    }


# ------------------------------------------------------------------ #
#  Telemetry anomalija (z-score vs rolling baseline)
# ------------------------------------------------------------------ #
def _telemetry_check(
    store: FleetSecurityStore,
    now: int,
    metric: str,
    z_threshold: float,
    min_samples: int,
    n: int,
) -> tuple[list[PostureFinding], list[str]]:
    """Per napravo: z-score zadnjega vzorca vs. base (pretekli vzorci).

    Vrne (findings, monitored_device_ids).
    """
    findings: list[PostureFinding] = []
    monitored: list[str] = []
    for device_id in sorted(store.monitor_device_ids()):
        rows = store.recent_telemetry(device_id, metric=metric, n=n)
        vals = [float(r["metrics"][metric]) for r in rows if metric in r["metrics"]]
        if len(vals) < min_samples:
            continue
        monitored.append(device_id)
        base, x = vals[:-1], vals[-1]
        if not base:
            continue
        try:
            z = z_score(base, x)
        except ValueError:
            continue
        if abs(z) >= z_threshold:
            severity = "high" if abs(z) >= ANOMALY_HIGH_Z else "medium"
            findings.append(
                PostureFinding(
                    device_id=device_id,
                    category="telemetry_anomaly",
                    severity=severity,
                    detail=f"metric={metric} value={x:.1f} z={z:.1f} window={len(vals)}",
                    detected_at=now,
                )
            )
    return findings, monitored


def detect_telemetry_anomalies(
    store: FleetSecurityStore,
    now: int | None = None,
    metric: str = "",
    z_threshold: float | None = None,
    min_samples: int | None = None,
    n: int | None = None,
) -> list[PostureFinding]:
    """Javni vmesnik: anomalije za eno metriko (defaulti iz settings)."""
    now = int(now) if now is not None else _now()
    zt = z_threshold if z_threshold is not None else settings.fs_anomaly_z_threshold
    ms = min_samples if min_samples is not None else settings.fs_anomaly_min_samples
    w = n if n is not None else settings.fs_telemetry_window
    findings, _ = _telemetry_check(store, now, metric, float(zt), int(ms), int(w))
    return findings


# ------------------------------------------------------------------ #
#  Egress detekcija (window-based first-seen + allowlist)
# ------------------------------------------------------------------ #
def _parse_allowlist(raw: str) -> list[str]:
    return [e.strip() for e in (raw or "").split(",") if e.strip()]


def _is_allowed(
    dst_host: str | None, dst_ip: str | None, entries: list[str]
) -> bool:
    """Ali je dst v allowlist (CIDR / IP / domain suffix)."""
    if not entries:
        return False
    candidates = [c for c in (dst_host, dst_ip) if c]
    for entry in entries:
        if "/" in entry:
            try:
                net = ip_network(entry, strict=False)
            except ValueError:
                continue
            for c in candidates:
                try:
                    if ip_address(c) in net:
                        return True
                except ValueError:
                    continue
        else:
            try:
                addr = ip_address(entry)
            except ValueError:
                for c in candidates:
                    if c == entry or c.endswith("." + entry):
                        return True
                continue
            for c in candidates:
                try:
                    if ip_address(c) == addr:
                        return True
                except ValueError:
                    continue
    return False


def _egress_check(
    store: FleetSecurityStore,
    now: int,
    allowlist: str,
    window_seconds: int | None,
) -> tuple[list[PostureFinding], list[str]]:
    """Window-based: dst v oknu, ne v known_before, ni v allowlist → finding.

    Vrne (findings, devices_with_events).
    """
    window = window_seconds or EGRESS_WINDOW_SECONDS
    entries = _parse_allowlist(allowlist)
    findings: list[PostureFinding] = []
    devices_with_events: list[str] = []
    for device_id in sorted(store.monitor_device_ids()):
        events = store.recent_network_events(device_id, since_ts=now - window)
        if not events:
            continue
        devices_with_events.append(device_id)
        known_before = store.known_destinations(device_id, before_ts=now - window)
        unknown: set[str] = set()
        for e in events:
            dst = e["dst_host"] or e["dst_ip"]
            if not dst:
                continue
            if dst in known_before:
                continue
            if _is_allowed(e["dst_host"], e["dst_ip"], entries):
                continue
            unknown.add(dst)
        for dst in sorted(unknown):
            findings.append(
                PostureFinding(
                    device_id=device_id,
                    category="unknown_egress",
                    severity="high",
                    detail=f"first-seen unknown destination {dst}",
                    detected_at=now,
                )
            )
        if len(unknown) >= EGRESS_BURST_THRESHOLD:
            findings.append(
                PostureFinding(
                    device_id=device_id,
                    category="egress_anomaly",
                    severity="medium",
                    detail=(
                        f"burst of {len(unknown)} unknown destinations in last {window}s"
                    ),
                    detected_at=now,
                )
            )
    return findings, devices_with_events


def detect_egress_anomalies(
    store: FleetSecurityStore,
    now: int | None = None,
    allowlist: str | None = None,
    window_seconds: int | None = None,
) -> list[PostureFinding]:
    """Javni vmesnik: egress najdbe (default allowlist iz settings)."""
    now = int(now) if now is not None else _now()
    al = allowlist if allowlist is not None else settings.fs_egress_allowlist
    findings, _ = _egress_check(store, now, al, window_seconds)
    return findings


# ------------------------------------------------------------------ #
#  Orchestracija
# ------------------------------------------------------------------ #
def run_monitor_pass(
    store: FleetSecurityStore,
    now: int | None = None,
    *,
    z_threshold: float | None = None,
    min_samples: int | None = None,
    allowlist: str | None = None,
    telemetry_window: int | None = None,
    telemetry_retention_hours: int | None = None,
    network_retention_hours: int | None = None,
    egress_window: int | None = None,
) -> dict:
    """En monitor pass: detektiraj + upsert (scope: monitor kategorije) + prune.

    Najdbe gredo v ISTI fs_findings tok; posture scoring se posodobi ob
    naslednjem ``run_assessment`` (daemon tick veriga oboje).
    """
    now = int(now) if now is not None else _now()
    zt = z_threshold if z_threshold is not None else settings.fs_anomaly_z_threshold
    ms = min_samples if min_samples is not None else settings.fs_anomaly_min_samples
    al = allowlist if allowlist is not None else settings.fs_egress_allowlist
    window_n = (
        telemetry_window
        if telemetry_window is not None
        else settings.fs_telemetry_window
    )
    ret_t = (
        telemetry_retention_hours
        if telemetry_retention_hours is not None
        else settings.fs_telemetry_retention_hours
    )
    ret_n = (
        network_retention_hours
        if network_retention_hours is not None
        else settings.fs_network_retention_hours
    )
    egress_win = egress_window or EGRESS_WINDOW_SECONDS

    findings: list[PostureFinding] = []
    monitored: set[str] = set(store.monitor_device_ids())

    # Union metrik čez naprave → za vsako telemetry check.
    all_metrics: set[str] = set()
    for device_id in store.monitor_device_ids():
        for row in store.recent_telemetry(device_id, n=window_n):
            all_metrics.update(row["metrics"].keys())
    for metric in sorted(all_metrics):
        f, m = _telemetry_check(store, now, metric, float(zt), int(ms), int(window_n))
        findings.extend(f)
        monitored.update(m)

    # Egress check.
    f2, dev2 = _egress_check(store, now, al, egress_win)
    findings.extend(f2)
    monitored.update(dev2)

    # Device-i z odprtimi monitor najdbami → da se stale razrešijo.
    for f in store.list_open_findings():
        if f.category in MONITOR_CATEGORIES:
            monitored.add(f.device_id)

    inserted = store.upsert_findings(
        findings,
        now=now,
        assessed=sorted(monitored),
        resolve_categories=MONITOR_CATEGORIES,
    )

    # Prune PO detekciji (known_before v oknu preživi).
    pruned_t = store.prune_telemetry(now - int(ret_t) * 3600)
    pruned_n = store.prune_network_events(now - int(ret_n) * 3600)

    try:
        audit.record(
            event="fleet-security-monitor",
            project="*",
            status="ok",
            detail=(
                f"findings={len(findings)} inserted={inserted} "
                f"devices={len(monitored)}"
            ),
        )
    except Exception:
        pass

    return {
        "findings_detected": len(findings),
        "findings_inserted": inserted,
        "monitored_devices": len(monitored),
        "pruned_telemetry": pruned_t,
        "pruned_network_events": pruned_n,
        "egress_window_seconds": egress_win,
    }


def monitor_summary(store: FleetSecurityStore) -> dict:
    """Povzetek monitorja: odprte anomalije + device števci."""
    open_findings = [
        f for f in store.list_open_findings() if f.category in MONITOR_CATEGORIES
    ]
    by_category: dict[str, int] = {}
    for f in open_findings:
        by_category[f.category] = by_category.get(f.category, 0) + 1
    return {
        "open_anomaly_findings": len(open_findings),
        "by_category": by_category,
        "telemetry_devices": store.telemetry_device_count(),
        "network_devices": store.network_device_count(),
        "egress_window_seconds": EGRESS_WINDOW_SECONDS,
    }
