"""fleet_security — dashboard snapshot testi (offline).

Konsolidiran JSON za TS panel: varni defaulti na prazni DB, napolnjen shape
z data, sortiranje + cap najdb.
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
from actions.fleet_security import dashboard, discovery, posture  # noqa: E402
from actions.fleet_security.schemas import HostInfo, OSInfo, PostureFinding  # noqa: E402

NOW = 1_700_000_000


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    monkeypatch.setattr(core_audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(core_quality, "ESCALATIONS_FILE", tmp_path / "escalations.json")
    monkeypatch.setattr(core_quality, "QUALITY_REGISTRY", tmp_path / "quality_registry.json")
    monkeypatch.setattr(core_quality, "REENABLE_GRACE_FILE", tmp_path / "reenable_grace.json")
    monkeypatch.setattr(settings, "fs_baselines_dir", str(tmp_path / "baselines"))
    monkeypatch.setattr(settings, "fs_db_path", str(tmp_path / "fs.db"))
    return str(tmp_path / "fs.db")


def _hostinfo(device_id="dev-1") -> HostInfo:
    return HostInfo(
        device_id=device_id,
        hostname="h1",
        role="worker",
        os=OSInfo(name="linux", version="5.15.2", kernel="5.15.2"),
        source="test",
        collected_at=NOW,
    )


def test_snapshot_empty_store_safe_defaults(db_path):
    data = dashboard.snapshot(db_path)
    # Vsi ključi obstajajo.
    assert data["fleet"]["device_count"] == 0
    assert data["fleet"]["mean_score"] is None
    assert data["findings"] == []
    assert data["findings_by_severity"] == {}
    assert len(data["cra"]) == 7                     # REQ-01..07
    assert data["monitor"]["open_anomaly_findings"] == 0
    assert data["redteam"]["runs"] == 0
    assert data["supplychain"]["history_records"] == 0
    assert data["threatintel"]["advisories"] >= 4    # seed feed
    assert data["threatintel"]["open_vulnerabilities"] == 0
    assert data["generated_at"]


def test_snapshot_populated_shape(db_path):
    from actions.fleet_security.store import FleetSecurityStore

    store = FleetSecurityStore(db_path)
    discovery.ingest_hostinfo(store, _hostinfo(), now=NOW)
    posture.run_assessment(store, now=NOW)
    store.upsert_findings(
        [
            PostureFinding(
                device_id="dev-1", category="config_drift", severity="high",
                detail="missing log_level", detected_at=NOW,
            )
        ],
        now=NOW,
    )

    data = dashboard.snapshot(db_path)
    assert data["fleet"]["device_count"] == 1
    assert data["fleet"]["mean_score"] is not None
    assert data["devices"][0]["device_id"] == "dev-1"
    assert data["devices"][0]["score"] is not None
    assert len(data["findings"]) == 1
    assert data["findings"][0]["severity"] == "high"
    assert data["findings_by_severity"].get("high", 0) >= 1


def test_snapshot_findings_sorted_and_capped(db_path):
    from actions.fleet_security.store import FleetSecurityStore

    store = FleetSecurityStore(db_path)
    findings = [
        PostureFinding(
            device_id="dev-1", category="config_drift", severity="medium",
            detail=f"f{i}", detected_at=NOW,
        )
        for i in range(25)
    ]
    findings.append(
        PostureFinding(
            device_id="dev-1", category="config_drift", severity="critical",
            detail="critical first", detected_at=NOW,
        )
    )
    store.upsert_findings(findings, now=NOW)

    data = dashboard.snapshot(db_path)
    assert len(data["findings"]) == dashboard._MAX_FINDINGS   # capped
    assert data["findings"][0]["severity"] == "critical"      # najhujša prva
