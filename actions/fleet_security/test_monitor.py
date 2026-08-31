"""fleet_security — Phase 2 monitor testi (vsi offline: tmp_path + monkeypatch).

Operator monitor (Skin A): telemetry ingest, z-score anomalija, egress
first-seen/allowlist/burst, monitor pass → posture score padec, retencija.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit as core_audit  # noqa: E402
from core import quality as core_quality  # noqa: E402
from core.config import settings  # noqa: E402
from actions.fleet_security import discovery, monitor, posture  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    HostInfo,
    NetworkObservation,
    OSInfo,
    TelemetrySample,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

NOW = 1_700_000_000


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(core_audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(core_quality, "ESCALATIONS_FILE", tmp_path / "escalations.json")
    monkeypatch.setattr(core_quality, "QUALITY_REGISTRY", tmp_path / "quality_registry.json")
    monkeypatch.setattr(core_quality, "REENABLE_GRACE_FILE", tmp_path / "reenable_grace.json")
    monkeypatch.setattr(settings, "fs_baselines_dir", str(tmp_path / "baselines"))
    return FleetSecurityStore(tmp_path / "fs.db")


def _hostinfo(device_id="dev-1") -> HostInfo:
    return HostInfo(
        device_id=device_id,
        hostname="h1",
        role="worker",
        os=OSInfo(name="linux", version="5.15", kernel="5.15.0"),
        source="test",
        collected_at=NOW,
    )


def _seed_cpu(store, device_id, values, start_ts=NOW):
    """Telemetry vzorce cpu_pct; vsak ob svojem ts."""
    for i, v in enumerate(values):
        monitor.ingest_telemetry(
            store,
            TelemetrySample(
                device_id=device_id, ts=start_ts + i, source="test",
                metrics={"cpu_pct": v},
            ),
            now=start_ts + i,
        )


# ------------------------------------------------------------------ #
#  Telemetry ingest + anomalija
# ------------------------------------------------------------------ #
def test_telemetry_ingest_and_audit(store):
    res = monitor.ingest_telemetry(
        store, TelemetrySample(device_id="dev-1", source="test", metrics={"cpu_pct": 42.0}),
        now=NOW,
    )
    assert res["device_id"] == "dev-1"
    rows = store.recent_telemetry("dev-1", n=10)
    assert len(rows) == 1 and rows[0]["metrics"]["cpu_pct"] == 42.0
    assert any(e["event"] == "fleet-security-telemetry" for e in core_audit.query())


def test_telemetry_anomaly_fires_on_outlier(store):
    _seed_cpu(store, "dev-1", [28.0, 29.0, 30.0, 31.0, 32.0, 29.5, 30.5, 28.5, 31.5])
    monitor.ingest_telemetry(
        store, TelemetrySample(device_id="dev-1", ts=NOW + 100, source="test", metrics={"cpu_pct": 97.0}),
        now=NOW + 100,
    )
    findings = monitor.detect_telemetry_anomalies(
        store, now=NOW + 100, metric="cpu_pct", min_samples=5, n=20
    )
    assert any(f.category == "telemetry_anomaly" and f.severity == "high" for f in findings)


def test_telemetry_anomaly_not_fired_below_min_samples(store):
    _seed_cpu(store, "dev-1", [30.0, 30.5, 29.5, 97.0])
    findings = monitor.detect_telemetry_anomalies(
        store, now=NOW + 10, metric="cpu_pct", min_samples=5, n=20
    )
    assert findings == []


def test_telemetry_anomaly_resolved_when_back_to_normal(store):
    _seed_cpu(store, "dev-1", [28.0, 29.0, 30.0, 31.0, 32.0, 29.5, 30.5, 28.5, 31.5])
    monitor.ingest_telemetry(
        store, TelemetrySample(device_id="dev-1", ts=NOW + 100, source="test", metrics={"cpu_pct": 97.0}),
        now=NOW + 100,
    )
    monitor.run_monitor_pass(
        store, now=NOW + 100, min_samples=5, telemetry_window=20, allowlist=""
    )
    assert any(f.category == "telemetry_anomaly" for f in store.list_open_findings("dev-1"))

    _seed_cpu(store, "dev-1", [30.0, 30.5, 29.8], start_ts=NOW + 200)
    monitor.run_monitor_pass(
        store, now=NOW + 210, min_samples=5, telemetry_window=20, allowlist=""
    )
    assert not any(
        f.category == "telemetry_anomaly" for f in store.list_open_findings("dev-1")
    )


# ------------------------------------------------------------------ #
#  Egress detekcija
# ------------------------------------------------------------------ #
def test_egress_first_seen_unknown_egress(store):
    monitor.ingest_network_observation(
        store,
        NetworkObservation(device_id="dev-1", ts=NOW, dst_host="evil.example.com",
                           dst_ip="10.0.0.9", dst_port=443, proto="tcp"),
        now=NOW,
    )
    findings = monitor.detect_egress_anomalies(
        store, now=NOW, allowlist="", window_seconds=3600
    )
    assert any(f.category == "unknown_egress" and f.severity == "high" for f in findings)


def test_egress_allowlist_suppresses(store):
    monitor.ingest_network_observation(
        store,
        NetworkObservation(device_id="dev-1", ts=NOW, dst_host="evil.example.com",
                           dst_ip="10.0.0.9", dst_port=443, proto="tcp"),
        now=NOW,
    )
    findings = monitor.detect_egress_anomalies(
        store, now=NOW, allowlist="evil.example.com", window_seconds=3600
    )
    assert not any(f.category == "unknown_egress" for f in findings)


def test_egress_known_dst_not_flagged(store):
    # Znan dst pred oknom → v oknu ni "first-seen".
    monitor.ingest_network_observation(
        store,
        NetworkObservation(device_id="dev-1", ts=NOW - 7200, dst_host="internal.example.com",
                           dst_ip="10.0.1.5", dst_port=443, proto="tcp"),
        now=NOW - 7200,
    )
    monitor.ingest_network_observation(
        store,
        NetworkObservation(device_id="dev-1", ts=NOW, dst_host="internal.example.com",
                           dst_ip="10.0.1.5", dst_port=443, proto="tcp"),
        now=NOW,
    )
    findings = monitor.detect_egress_anomalies(
        store, now=NOW, allowlist="", window_seconds=3600
    )
    assert not any(f.category == "unknown_egress" for f in findings)


def test_egress_burst_anomaly(store):
    for i in range(6):
        monitor.ingest_network_observation(
            store,
            NetworkObservation(device_id="dev-1", ts=NOW + i, dst_host=f"c2-{i}.example.com",
                               dst_ip=f"10.0.0.{i + 1}", dst_port=443, proto="tcp"),
            now=NOW + i,
        )
    findings = monitor.detect_egress_anomalies(
        store, now=NOW + 10, allowlist="", window_seconds=3600
    )
    assert sum(1 for f in findings if f.category == "unknown_egress") == 6
    assert any(f.category == "egress_anomaly" for f in findings)


# ------------------------------------------------------------------ #
#  Monitor pass → posture + retencija
# ------------------------------------------------------------------ #
def test_monitor_pass_drops_posture_score(store):
    discovery.ingest_hostinfo(store, _hostinfo(), now=NOW)
    posture.run_assessment(store, now=NOW)
    assert store.latest_score("dev-1").score == 100

    _seed_cpu(store, "dev-1", [28.0, 29.0, 30.0, 31.0, 32.0, 29.5, 30.5, 28.5, 31.5])
    monitor.ingest_telemetry(
        store, TelemetrySample(device_id="dev-1", ts=NOW + 100, source="test", metrics={"cpu_pct": 97.0}),
        now=NOW + 100,
    )
    monitor.run_monitor_pass(
        store, now=NOW + 100, min_samples=5, telemetry_window=20, allowlist=""
    )
    # Reassess: monitor najdbe (high) znižajo score.
    posture.run_assessment(store, now=NOW + 100)
    assert store.latest_score("dev-1").score < 100


def test_monitor_pass_prunes_retention(store):
    monitor.ingest_telemetry(
        store, TelemetrySample(device_id="dev-1", ts=NOW - 10 * 3600, source="test", metrics={"cpu_pct": 1.0}),
        now=NOW,
    )
    monitor.ingest_network_observation(
        store,
        NetworkObservation(device_id="dev-1", ts=NOW - 10 * 3600, dst_host="old.example.com",
                           dst_ip="10.0.0.1", dst_port=443, proto="tcp"),
        now=NOW,
    )
    monitor.run_monitor_pass(
        store, now=NOW, telemetry_retention_hours=1, network_retention_hours=1, allowlist=""
    )
    assert store.recent_telemetry("dev-1", n=10) == []
    assert store.recent_network_events("dev-1") == []


def test_monitor_pass_does_not_clobber_posture_findings(store):
    """Monitor pass ne sme resolve-ati posture najdb (cross-category scope)."""
    discovery.ingest_hostinfo(store, _hostinfo(), now=NOW)
    # Posture finding: config_drift prek baseline-a.
    from actions.fleet_security.schemas import Baseline

    store.upsert_baseline(Baseline(role="worker", required_config_keys={"log_level": "info"}))
    posture.run_assessment(store, now=NOW)
    assert any(f.category == "config_drift" for f in store.list_open_findings("dev-1"))

    # Monitor pass brez najdb → posture config_drift mora ostati odprt.
    monitor.run_monitor_pass(store, now=NOW, allowlist="")
    assert any(f.category == "config_drift" for f in store.list_open_findings("dev-1"))
