"""fleet_security — Phase 3 threat intel testi (offline).

Version comparison (determinističen), seed feed load, version→vuln mapiranje,
severity iz CVSS, resolve ko fixed, ne-clobber drugih modulov.
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
from actions.fleet_security import compliance, monitor, threatintel  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    FirmwareInfo,
    HostInfo,
    NetworkObservation,
    OSInfo,
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


def _hostinfo(device_id="dev-1", os_name="windows", os_version="10",
              firmware=None, model=None) -> HostInfo:
    return HostInfo(
        device_id=device_id,
        hostname="h1",
        role="worker",
        os=OSInfo(name=os_name, version=os_version, kernel="10"),
        firmware=firmware or [],
        model=model,
        source="test",
        collected_at=NOW,
    )


# ------------------------------------------------------------------ #
#  Version comparison
# ------------------------------------------------------------------ #
def test_compare_versions_numeric():
    assert threatintel.compare_versions("1.2.3", "1.2.4") < 0
    assert threatintel.compare_versions("1.10", "1.9") > 0
    assert threatintel.compare_versions("1.2", "1.2.0") == 0
    assert threatintel.compare_versions("2.0", "1.9.9") > 0


def test_compare_versions_non_numeric():
    assert threatintel.compare_versions("v1.2", "1.2") == 0
    assert threatintel.compare_versions("2026.08.31", "2026.08.30") > 0
    # Deterministično: non-numeric segment sortira za numeric (semver pre-release
    # ordering namerno ni implementiran).
    assert threatintel.compare_versions("1.2.3-beta", "1.2.3") > 0


# ------------------------------------------------------------------ #
#  Feed + mapiranje
# ------------------------------------------------------------------ #
def test_load_feed_default_path():
    feed = threatintel.load_feed()
    assert len(feed) == 4
    assert all(a.cve_id for a in feed)
    assert any(a.component == "motor-controller" for a in feed)


def test_check_threat_feed_matches_firmware_critical(store):
    from actions.fleet_security import discovery

    discovery.ingest_hostinfo(
        store,
        _hostinfo(firmware=[FirmwareInfo(component="motor-controller", version="1.0.1")]),
        now=NOW,
    )
    findings = threatintel.check_threat_feed(store, now=NOW)
    crit = [f for f in findings if f.severity == "critical"]
    assert any(f.category == "known_vulnerability" for f in crit)
    assert any("CVE-2026-1001" in f.detail for f in crit)


def test_check_threat_feed_fixed_in_not_affected(store):
    from actions.fleet_security import discovery

    discovery.ingest_hostinfo(
        store,
        _hostinfo(firmware=[FirmwareInfo(component="motor-controller", version="1.1.1")]),
        now=NOW,
    )
    findings = threatintel.check_threat_feed(store, now=NOW)
    assert not any("motor-controller" in f.detail for f in findings)


def test_check_threat_feed_severity_bands(store):
    from actions.fleet_security import discovery

    discovery.ingest_hostinfo(
        store,
        _hostinfo("dev-crit", firmware=[FirmwareInfo(component="motor-controller", version="1.0.1")]),
        now=NOW,
    )
    discovery.ingest_hostinfo(
        store, _hostinfo("dev-high", os_name="linux", os_version="5.15.0"), now=NOW
    )
    discovery.ingest_hostinfo(
        store,
        _hostinfo("dev-low", firmware=[FirmwareInfo(component="bms-firmware", version="1.0.0")]),
        now=NOW,
    )
    findings = threatintel.check_threat_feed(store, now=NOW)
    severities = {f.device_id: f.severity for f in findings}
    assert severities.get("dev-crit") == "critical"   # cvss 9.8
    assert severities.get("dev-high") == "high"       # cvss 7.5
    assert severities.get("dev-low") == "low"         # cvss 3.1


def test_check_threat_feed_resolves_when_fixed(store):
    from actions.fleet_security import discovery

    discovery.ingest_hostinfo(
        store,
        _hostinfo(firmware=[FirmwareInfo(component="motor-controller", version="1.0.1")]),
        now=NOW,
    )
    threatintel.run_threatintel_pass(store, now=NOW)
    assert any(f.category == "known_vulnerability" for f in store.list_open_findings("dev-1"))
    # Nadgradnja na fixed → resolve.
    discovery.ingest_hostinfo(
        store,
        _hostinfo(firmware=[FirmwareInfo(component="motor-controller", version="1.1.1")]),
        now=NOW + 100,
    )
    threatintel.run_threatintel_pass(store, now=NOW + 100)
    assert not any(
        f.category == "known_vulnerability" for f in store.list_open_findings("dev-1")
    )


# ------------------------------------------------------------------ #
#  Ne-clobber + compliance
# ------------------------------------------------------------------ #
def test_threatintel_no_clobber_monitor(store):
    monitor.ingest_network_observation(
        store,
        NetworkObservation(device_id="dev-1", ts=NOW, dst_host="evil.example.com",
                           dst_ip="10.0.0.9", dst_port=443, proto="tcp"),
        now=NOW,
    )
    monitor.run_monitor_pass(store, now=NOW, allowlist="")
    assert any(f.category == "unknown_egress" for f in store.list_open_findings("dev-1"))
    threatintel.run_threatintel_pass(store, now=NOW)
    assert any(f.category == "unknown_egress" for f in store.list_open_findings("dev-1"))


def test_threatintel_compliance_req02(store):
    from actions.fleet_security import discovery

    discovery.ingest_hostinfo(
        store, _hostinfo("dev-1", os_name="linux", os_version="5.15.0"), now=NOW
    )
    threatintel.run_threatintel_pass(store, now=NOW)
    assert any(f.severity == "high" for f in store.list_open_findings("dev-1"))
    data = compliance.generate_report_json(store, now=NOW)
    req02 = next(r for r in data["requirements"] if r["requirement_id"] == "REQ-02")
    assert req02["status"] == "non_compliant"
