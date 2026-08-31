"""fleet_security — Phase 3 supply-chain testi (offline).

Provenance registry + change detekcija: first-seen → baseline brez findinga,
sha256/version drift → model_changed (stabilen detail → dedup), prazno sha256 →
model_unverified. Resolve samo prek eksplicitnega record_model.
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
from actions.fleet_security import compliance, discovery, posture, supplychain  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    Baseline,
    HostInfo,
    ModelInfo,
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


def _hostinfo_with_model(device_id="dev-1", version="1.0", sha256="A" * 64) -> HostInfo:
    return HostInfo(
        device_id=device_id,
        hostname="h1",
        role="worker",
        os=OSInfo(name="linux", version="5.15", kernel="5.15.0"),
        model=ModelInfo(name="vision-model", version=version, provider="oem", sha256=sha256),
        source="test",
        collected_at=NOW,
    )


# ------------------------------------------------------------------ #
#  Provenance registry
# ------------------------------------------------------------------ #
def test_record_model_first(store):
    model = ModelInfo(name="m", version="1.0", provider="oem", sha256="A" * 64)
    row_id = supplychain.record_model(store, "dev-1", model, pushed_by="ci", now=NOW)
    assert row_id > 0
    latest = store.latest_model_record("dev-1")
    assert latest is not None and latest["sha256"] == "A" * 64


def test_record_model_noop_same_sha_version(store):
    model = ModelInfo(name="m", version="1.0", provider="oem", sha256="A" * 64)
    supplychain.record_model(store, "dev-1", model, now=NOW)
    row_id = supplychain.record_model(store, "dev-1", model, now=NOW + 10)
    assert row_id == 0
    assert len(store.list_model_history("dev-1")) == 1


def test_record_model_appends_on_change(store):
    supplychain.record_model(
        store, "dev-1", ModelInfo(name="m", version="1.0", provider="oem", sha256="A" * 64), now=NOW
    )
    supplychain.record_model(
        store, "dev-1", ModelInfo(name="m", version="2.0", provider="oem", sha256="B" * 64), now=NOW + 10
    )
    assert len(store.list_model_history("dev-1")) == 2


# ------------------------------------------------------------------ #
#  Check / change detekcija
# ------------------------------------------------------------------ #
def test_check_first_seen_records_no_finding(store):
    discovery.ingest_hostinfo(store, _hostinfo_with_model(), now=NOW)
    res = supplychain.run_supplychain_pass(store, now=NOW)
    assert res["findings_detected"] == 0
    assert len(store.list_model_history("dev-1")) == 1  # baseline record


def test_check_model_changed_finding_stable(store):
    discovery.ingest_hostinfo(store, _hostinfo_with_model(version="1.0", sha256="A" * 64), now=NOW)
    supplychain.run_supplychain_pass(store, now=NOW)
    # Sprememba modela (v2 sha B).
    discovery.ingest_hostinfo(store, _hostinfo_with_model(version="2.0", sha256="B" * 64), now=NOW + 100)
    supplychain.run_supplychain_pass(store, now=NOW + 100)
    changed = [f for f in store.list_open_findings("dev-1") if f.category == "model_changed"]
    assert len(changed) == 1 and changed[0].severity == "high"
    # Drugi pass → še vedno ena odprta (stabilen detail → dedup).
    supplychain.run_supplychain_pass(store, now=NOW + 200)
    changed2 = [f for f in store.list_open_findings("dev-1") if f.category == "model_changed"]
    assert len(changed2) == 1


def test_check_model_unverified_empty_sha(store):
    discovery.ingest_hostinfo(store, _hostinfo_with_model(version="1.0", sha256=""), now=NOW)
    supplychain.run_supplychain_pass(store, now=NOW)
    unverified = [f for f in store.list_open_findings("dev-1") if f.category == "model_unverified"]
    assert len(unverified) == 1 and unverified[0].severity == "medium"


def test_model_changed_resolves_after_record(store):
    discovery.ingest_hostinfo(store, _hostinfo_with_model(version="1.0", sha256="A" * 64), now=NOW)
    supplychain.run_supplychain_pass(store, now=NOW)
    discovery.ingest_hostinfo(store, _hostinfo_with_model(version="2.0", sha256="B" * 64), now=NOW + 100)
    supplychain.run_supplychain_pass(store, now=NOW + 100)
    assert any(f.category == "model_changed" for f in store.list_open_findings("dev-1"))
    # Operater/CI eksplicitno zabeleži nov artifact.
    supplychain.record_model(
        store, "dev-1",
        ModelInfo(name="vision-model", version="2.0", provider="oem", sha256="B" * 64),
        pushed_by="ci", now=NOW + 200,
    )
    supplychain.run_supplychain_pass(store, now=NOW + 200)
    assert not any(
        f.category == "model_changed" for f in store.list_open_findings("dev-1")
    )


# ------------------------------------------------------------------ #
#  Ne-clobber + compliance
# ------------------------------------------------------------------ #
def test_supplychain_no_clobber_posture(store):
    discovery.ingest_hostinfo(store, _hostinfo_with_model(), now=NOW)
    store.upsert_baseline(Baseline(role="worker", required_config_keys={"log_level": "info"}))
    posture.run_assessment(store, now=NOW)
    assert any(f.category == "config_drift" for f in store.list_open_findings("dev-1"))
    supplychain.run_supplychain_pass(store, now=NOW)
    assert any(f.category == "config_drift" for f in store.list_open_findings("dev-1"))


def test_supplychain_compliance_req04(store):
    discovery.ingest_hostinfo(store, _hostinfo_with_model(version="1.0", sha256="A" * 64), now=NOW)
    supplychain.run_supplychain_pass(store, now=NOW)
    discovery.ingest_hostinfo(store, _hostinfo_with_model(version="2.0", sha256="B" * 64), now=NOW + 100)
    supplychain.run_supplychain_pass(store, now=NOW + 100)
    assert any(f.category == "model_changed" for f in store.list_open_findings("dev-1"))
    data = compliance.generate_report_json(store, now=NOW + 100)
    req04 = next(r for r in data["requirements"] if r["requirement_id"] == "REQ-04")
    assert req04["status"] == "partial"
