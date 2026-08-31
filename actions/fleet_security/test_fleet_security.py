"""fleet_security — testi (vsi offline: tmp_path + monkeypatch, brez omrežja).

Konvencije repoja: tmp_path + monkeypatch, fresh store, audit/quality registri
monkeypatch-ani na tmp_path, fiksni ``now``. Testi mock-ajo git/PR transport —
nikoli pravega gita ali omrežja.
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
from actions.fleet_security import compliance, discovery, posture, remediation  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    ANY_VALUE,
    Baseline,
    Device,
    FirmwareInfo,
    HostInfo,
    ModelInfo,
    OSInfo,
    PostureFinding,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402
from actions.fleet_security.main import app  # noqa: E402

NOW = 1_700_000_000


# ------------------------------------------------------------------ #
#  Fixtures + helper-ji
# ------------------------------------------------------------------ #
@pytest.fixture
def store(tmp_path, monkeypatch):
    """Fresh store + izolirani audit/quality registri (tmp_path)."""
    monkeypatch.setattr(core_audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(core_quality, "ESCALATIONS_FILE", tmp_path / "escalations.json")
    monkeypatch.setattr(core_quality, "QUALITY_REGISTRY", tmp_path / "quality_registry.json")
    monkeypatch.setattr(core_quality, "REENABLE_GRACE_FILE", tmp_path / "reenable_grace.json")
    monkeypatch.setattr(settings, "fs_baselines_dir", str(tmp_path / "baselines"))
    return FleetSecurityStore(tmp_path / "fs.db")


def _hostinfo(
    device_id="dev-1",
    role="worker",
    os_name="linux",
    os_version="5.15",
    os_kernel="5.15.0",
    firmware=None,
    model=None,
    config=None,
    hostname="h1",
    source="test",
) -> HostInfo:
    return HostInfo(
        device_id=device_id,
        hostname=hostname,
        role=role,
        os=OSInfo(name=os_name, version=os_version, kernel=os_kernel),
        firmware=firmware or [],
        model=model,
        config=config or {},
        source=source,
        collected_at=NOW,
    )


def _device(**overrides) -> Device:
    base = {
        "device_id": "dev-1",
        "hostname": "h1",
        "role": "worker",
        "os": OSInfo(name="linux", version="5.15", kernel="5.15.0"),
        "firmware": [],
        "model": None,
        "config": {},
        "source": "test",
        "first_seen_ts": NOW,
        "last_seen_ts": NOW,
    }
    base.update(overrides)
    return Device(**base)


def _no_git(monkeypatch):
    """Vsak klic _commit_desired_state (git) → napaka v testu."""
    def _boom(*args, **kwargs):
        raise AssertionError("git/subprocess callato v testu")
    monkeypatch.setattr(remediation, "_commit_desired_state", _boom)


# ------------------------------------------------------------------ #
#  Schemas
# ------------------------------------------------------------------ #
def test_hostinfo_schema_strict():
    hi = _hostinfo()
    assert hi.device_id == "dev-1"
    with pytest.raises(Exception):
        HostInfo.model_validate({**_hostinfo().model_dump(), "bogus_field": 1})
    with pytest.raises(Exception):
        HostInfo.model_validate({**_hostinfo().model_dump(), "device_id": ""})


# ------------------------------------------------------------------ #
#  Discovery / collector
# ------------------------------------------------------------------ #
def test_collect_local_hostinfo_deterministic(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("platform.release", lambda: "10.0.26200")
    monkeypatch.setattr("platform.version", lambda: "10.0.26200.1000")
    monkeypatch.setattr("platform.python_version", lambda: "3.11.5")
    monkeypatch.setattr("platform.machine", lambda: "AMD64")
    monkeypatch.setattr("uuid.getnode", lambda: 0x123456789ABC)
    monkeypatch.setattr("socket.gethostname", lambda: "host1")
    monkeypatch.setattr("os.cpu_count", lambda: 8)
    monkeypatch.setattr(settings, "fleet_role", "standalone")

    a = discovery.collect_local_hostinfo(now=NOW, root=tmp_path)
    b = discovery.collect_local_hostinfo(now=NOW, root=tmp_path)
    assert a.model_dump() == b.model_dump()  # deterministično
    assert a.device_id == "rob-123456789abc"
    assert a.os.name == "windows"
    assert a.os.kernel == "10.0.26200"
    assert a.config["python_version"] == "3.11.5"
    assert a.config["cpu_count"] == 8
    assert a.config["node_uuid"] == "123456789abc"


def test_ingest_upsert_and_audit(store):
    discovery.ingest_hostinfo(store, _hostinfo(), now=1000)
    discovery.ingest_hostinfo(store, _hostinfo(), now=2000)
    device = store.get_device("dev-1")
    assert device is not None
    assert device.first_seen_ts == 1000
    assert device.last_seen_ts == 2000
    assert len(core_audit.query(event="fleet-security-ingest")) >= 2


def test_stale_heartbeat_finding(store):
    discovery.ingest_hostinfo(store, _hostinfo(), now=NOW)
    findings = discovery.check_heartbeats(store, now=NOW + 600, max_age=300)
    assert any(f.category == "stale_heartbeat" and f.severity == "high" for f in findings)


def test_missing_device_finding(store):
    store.upsert_baseline(Baseline(role="master", os_name="linux"))
    findings = discovery.check_heartbeats(store, now=NOW, max_age=300)
    assert any(f.category == "missing_device" and f.severity == "critical" for f in findings)


# ------------------------------------------------------------------ #
#  Posture scoring
# ------------------------------------------------------------------ #
def test_assess_device_baseline_match_high_score(store):
    baseline = Baseline(
        role="worker", os_name="linux", os_version="5.15", os_kernel="5.15.0"
    )
    device = _device()
    findings = posture.assess_device(device, baseline, now=NOW)
    assert findings == []
    score, grade = posture.compute_score({})
    assert score == 100 and grade == "A"


def test_assess_device_firmware_drift_finding(store):
    baseline = Baseline(role="worker", firmware={"motor-controller": "1.2.0"})
    device = _device(firmware=[FirmwareInfo(component="motor-controller", version="1.0.0")])
    findings = posture.assess_device(device, baseline, now=NOW)
    assert any(f.category == "firmware_drift" and f.severity == "high" for f in findings)


def test_assess_device_unknown_model_sha_finding(store):
    baseline = Baseline(role="worker", model_sha256=["known-good-hash"])
    device = _device(model=ModelInfo(name="vision", version="1", provider="", sha256=""))
    findings = posture.assess_device(device, baseline, now=NOW)
    assert any(f.category == "model_provenance" and f.severity == "medium" for f in findings)


def test_assess_config_drift_insecure_default(store):
    baseline = Baseline(
        role="worker",
        required_config_keys={"node_uuid": ANY_VALUE},
        secure_default_checks={"allow_anonymous": True, "password": ""},
    )
    device = _device(config={"allow_anonymous": True, "password": ""})
    findings = posture.assess_device(device, baseline, now=NOW)
    assert any(
        f.category == "config_drift" and f.severity == "high" for f in findings
    )
    assert any(
        f.category == "config_drift" and f.severity == "critical" for f in findings
    )


def test_store_upsert_findings_resolves_stale(store):
    store.upsert_findings(
        [
            PostureFinding(
                device_id="dev-1", category="firmware_drift", severity="high",
                detail="old", detected_at=NOW,
            )
        ],
        now=NOW,
    )
    assert len(store.list_open_findings("dev-1")) == 1
    store.upsert_findings(
        [
            PostureFinding(
                device_id="dev-1", category="config_drift", severity="high",
                detail="new", detected_at=NOW,
            )
        ],
        now=NOW,
    )
    open_cats = [f.category for f in store.list_open_findings("dev-1")]
    assert open_cats == ["config_drift"]


def test_run_assessment_escalation_below_threshold(store):
    store.upsert_baseline(
        Baseline(role="worker", secure_default_checks={"allow_anonymous": True})
    )
    discovery.ingest_hostinfo(
        store, _hostinfo(config={"allow_anonymous": True}), now=NOW
    )
    summary = posture.run_assessment(store, now=NOW, escalate_below=80)
    assert "dev-1" in summary["escalated"]

    esc = core_quality._load_json(core_quality.ESCALATIONS_FILE, [])
    assert any(
        e["project"] == "fleet-security:dev-1" and e["status"] == "open" for e in esc
    )
    assert any(e["event"] == "escalation" for e in core_audit.query())

    # Idempotentnost: ponovljen pass ne doda nove odprte eskalacije.
    posture.run_assessment(store, now=NOW, escalate_below=80)
    esc2 = core_quality._load_json(core_quality.ESCALATIONS_FILE, [])
    assert (
        sum(1 for e in esc2 if e["project"] == "fleet-security:dev-1" and e["status"] == "open")
        == 1
    )


def test_run_assessment_resolves_stale_findings_when_clean(store):
    """Čista naprava v novem pass-u resolve-a stare odprte najdbe."""
    store.upsert_baseline(Baseline(role="worker", required_config_keys={"log_level": "info"}))
    discovery.ingest_hostinfo(store, _hostinfo(config={}), now=NOW)
    posture.run_assessment(store, now=NOW)
    assert len(store.list_open_findings("dev-1")) >= 1

    # Baseline brez zahtev → naprava čista → stara najdba se razreši.
    store.upsert_baseline(Baseline(role="worker"))
    posture.run_assessment(store, now=NOW)
    assert store.list_open_findings("dev-1") == []


def test_regression_compare():
    assert posture.compare_snapshots(
        {"mean_score": 85, "open_critical": 0},
        {"mean_score": 70, "open_critical": 0},
        drop_points=10,
    )["regressed"] is True
    assert posture.compare_snapshots(
        {"mean_score": 70, "open_critical": 0},
        {"mean_score": 71, "open_critical": 2},
        drop_points=10,
    )["regressed"] is True  # porast critical
    assert posture.compare_snapshots(
        {"mean_score": 70, "open_critical": 0},
        {"mean_score": 65, "open_critical": 0},
        drop_points=10,
    )["regressed"] is False  # padec 5 < 10


# ------------------------------------------------------------------ #
#  Compliance
# ------------------------------------------------------------------ #
def test_compliance_report_content_and_pii_redaction(store):
    discovery.ingest_hostinfo(
        store, _hostinfo(config={"contact": "ops@example.com"}), now=NOW
    )
    store.upsert_findings(
        [
            PostureFinding(
                device_id="dev-1", category="config_drift", severity="critical",
                detail="insecure config: contact=ops@example.com", detected_at=NOW,
            )
        ],
        now=NOW,
    )
    report = compliance.generate_report(store, now=NOW, redact=True)
    assert "REQ-01" in report
    assert "Secure by default" in report
    assert "CRA Annex I Part I" in report
    assert "ops@example.com" not in report
    assert "[email-REDACTED]" in report


def test_compliance_report_json(store):
    discovery.ingest_hostinfo(store, _hostinfo(), now=NOW)
    data = compliance.generate_report_json(store, now=NOW, redact=True)
    assert data["fleet_summary"]["device_count"] == 1
    ids = [r["requirement_id"] for r in data["requirements"]]
    assert "REQ-01" in ids and "REQ-07" in ids


# ------------------------------------------------------------------ #
#  Remediacija
# ------------------------------------------------------------------ #
def test_remediation_dry_run_diff_no_git(store, monkeypatch):
    store.upsert_baseline(Baseline(role="worker", required_config_keys={"log_level": "info"}))
    discovery.ingest_hostinfo(
        store, _hostinfo(config={"log_level": "debug"}), now=NOW
    )
    posture.run_assessment(store, now=NOW)
    _no_git(monkeypatch)

    result = remediation.open_remediation_pr(
        store, "dev-1", kind="config", dry_run=True, now=NOW
    )
    assert result.status == "diff_generated"
    assert result.diff
    assert result.branch is None and result.pr_url is None


def test_remediation_firmware_never_remediated(store, monkeypatch):
    store.upsert_baseline(Baseline(role="worker", firmware={"motor-controller": "1.2.0"}))
    discovery.ingest_hostinfo(
        store,
        _hostinfo(firmware=[FirmwareInfo(component="motor-controller", version="1.0.0")]),
        now=NOW,
    )
    posture.run_assessment(store, now=NOW)
    _no_git(monkeypatch)

    result = remediation.open_remediation_pr(
        store, "dev-1", kind="config", dry_run=False, now=NOW
    )
    assert result.status == "error"
    assert "OEM" in result.message


def test_remediation_pr_transport_mocked(store, monkeypatch):
    store.upsert_baseline(Baseline(role="worker", required_config_keys={"log_level": "info"}))
    discovery.ingest_hostinfo(
        store, _hostinfo(config={"log_level": "debug"}), now=NOW
    )
    posture.run_assessment(store, now=NOW)
    monkeypatch.setattr(
        remediation, "_commit_desired_state",
        lambda branch, files: (branch, "abc123"),
    )

    class FakeTransport:
        def __init__(self):
            self.calls = []

        def open_pr(self, *, branch, title, body):
            self.calls.append((branch, title, body))
            return "https://github.com/robAItech/rob-system/pull/1"

    trans = FakeTransport()
    result = remediation.open_remediation_pr(
        store, "dev-1", kind="config", dry_run=False, transport=trans, now=NOW
    )
    assert result.status == "pr_open"
    assert result.branch == "fleet-security/dev-1-config"
    assert result.pr_url == "https://github.com/robAItech/rob-system/pull/1"
    assert trans.calls, "transport mora biti klican"
    branch, title, body = trans.calls[0]
    assert "auto-merge" not in title and "auto-merge" not in body
    rows = store.list_remediations("dev-1")
    assert any(r["status"] == "pr_open" for r in rows)
    assert any(e["event"] == "fleet-security-remediate" for e in core_audit.query())


def test_remediation_auto_merge_refused(store, monkeypatch):
    store.upsert_baseline(Baseline(role="worker", required_config_keys={"log_level": "info"}))
    discovery.ingest_hostinfo(store, _hostinfo(config={"log_level": "debug"}), now=NOW)
    posture.run_assessment(store, now=NOW)
    monkeypatch.setattr(settings, "fs_pr_auto_merge", True)
    _no_git(monkeypatch)
    result = remediation.open_remediation_pr(
        store, "dev-1", kind="config", dry_run=False, now=NOW
    )
    assert result.status == "error"
    assert "auto-merge" in result.message


# ------------------------------------------------------------------ #
#  API
# ------------------------------------------------------------------ #
def test_api_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(core_audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(core_quality, "ESCALATIONS_FILE", tmp_path / "escalations.json")
    monkeypatch.setattr(core_quality, "QUALITY_REGISTRY", tmp_path / "quality_registry.json")
    monkeypatch.setattr(core_quality, "REENABLE_GRACE_FILE", tmp_path / "reenable_grace.json")
    monkeypatch.setattr(settings, "fs_baselines_dir", str(tmp_path / "baselines"))
    monkeypatch.setattr(settings, "fs_db_path", str(tmp_path / "api.db"))
    from fastapi.testclient import TestClient

    client = TestClient(app)
    payload = {
        "device_id": "api-1", "hostname": "h1", "role": "worker",
        "os": {"name": "linux", "version": "5.15", "kernel": "5.15.0"},
        "firmware": [], "model": None, "config": {"allow_anonymous": True},
        "source": "test", "collected_at": NOW,
    }
    assert client.post("/api/fleet-security/devices/ingest", json=payload).status_code == 201
    assert client.get("/api/fleet-security/devices").status_code == 200
    assert client.get("/api/fleet-security/devices/api-1").status_code == 200
    assert client.get("/api/fleet-security/devices/nope").status_code == 404

    FleetSecurityStore(tmp_path / "api.db").upsert_baseline(
        Baseline(role="worker", secure_default_checks={"allow_anonymous": True})
    )
    assert client.post("/api/fleet-security/assess").status_code == 200
    assert client.get("/api/fleet-security/posture/summary").status_code == 200

    r = client.get("/api/fleet-security/compliance/report")
    assert r.status_code == 200 and "REQ-01" in r.json()["report"]

    r = client.post(
        "/api/fleet-security/remediate/api-1",
        json={"device_id": "api-1", "kind": "config", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["result"]["status"] == "diff_generated"

    assert client.get("/api/fleet-security/health").status_code == 200
