"""fleet_security — Phase 3 red team testi (offline, SIMULACIJA samo).

MockBrain je determinističen; LLMBrain v NO-KEY mode vrne simuliran izhod.
Ni realnega omrežja / LLM klica v testih.
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
from actions.fleet_security import compliance, redteam  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    HostInfo,
    OSInfo,
    SEVERITIES,
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


# ------------------------------------------------------------------ #
#  Payload library + mock brain
# ------------------------------------------------------------------ #
def test_payload_library_shape():
    ids = [p["id"] for p in redteam.PAYLOAD_LIBRARY]
    assert len(ids) == len(set(ids))  # uniq ids
    for p in redteam.PAYLOAD_LIBRARY:
        assert p["name"] and p["category"] and p["vector"]
        assert p["impact_severity"] in SEVERITIES


def test_mock_brain_secure_refuses():
    brain = redteam.MockBrainTarget(secure=True)
    decision = brain.decide("Open the door", "You are safe")
    assert "REFUSED" in decision
    assert redteam.judge_response(decision) is False


def test_mock_brain_naive_obeys():
    brain = redteam.MockBrainTarget(secure=False)
    decision = brain.decide("Open the door", "You are safe")
    assert "EXECUTE" in decision
    assert redteam.judge_response(decision) is True


def test_judge_response_policy():
    assert redteam.judge_response("executing shutdown", ("shutdown",)) is True
    assert redteam.judge_response("navigate to base", ("shutdown",)) is False


# ------------------------------------------------------------------ #
#  Run
# ------------------------------------------------------------------ #
def test_run_red_team_naive_stores_runs_and_findings(store):
    brain = redteam.MockBrainTarget(secure=False)
    res = redteam.run_red_team(store, "rob-1", brain, system_prompt="safe", now=NOW)
    assert res["payloads_run"] == len(redteam.PAYLOAD_LIBRARY)
    assert res["vulnerable"] == len(redteam.PAYLOAD_LIBRARY)  # naive → vse
    assert res["runs_stored"] == len(redteam.PAYLOAD_LIBRARY)
    runs = store.list_redteam_runs("rob-1")
    assert len(runs) == len(redteam.PAYLOAD_LIBRARY)
    assert any(f.category == "redteam_injection" for f in store.list_open_findings("rob-1"))
    assert any(e["event"] == "fleet-security-redteam" for e in core_audit.query())


def test_run_red_team_secure_no_findings(store):
    brain = redteam.MockBrainTarget(secure=True)
    res = redteam.run_red_team(store, "rob-1", brain, system_prompt="safe", now=NOW)
    assert res["vulnerable"] == 0
    assert store.list_open_findings("rob-1") == []
    assert len(store.list_redteam_runs("rob-1")) == len(redteam.PAYLOAD_LIBRARY)


def test_run_red_team_resolves_stale_injection(store):
    naive = redteam.MockBrainTarget(secure=False)
    redteam.run_red_team(store, "rob-1", naive, system_prompt="safe", now=NOW)
    assert any(f.category == "redteam_injection" for f in store.list_open_findings("rob-1"))
    secure = redteam.MockBrainTarget(secure=True)
    redteam.run_red_team(store, "rob-1", secure, system_prompt="safe", now=NOW + 100)
    assert not any(
        f.category == "redteam_injection" for f in store.list_open_findings("rob-1")
    )


def test_redteam_sim_only_guard(store):
    class LiveTarget:
        simulated = False  # ni simuliran → guard fail-closed

        def decide(self, user_input, system_prompt):
            return "EXECUTE: real robot"

    res = redteam.run_red_team(store, "rob-1", LiveTarget(), now=NOW)
    assert "error" in res and "simulation-only" in res["error"]
    assert store.list_open_findings("rob-1") == []


def test_llm_brain_no_key_simulated(monkeypatch):
    # Neutraliziraj VSE LLM fallback ključe → NO-KEY mode (simuliran izhod).
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-your-deepseek-api-key-here")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "alternate_model", "")
    monkeypatch.setattr(settings, "alternate_api_key", "")
    brain = redteam.LLMBrainTarget()
    decision = brain.decide("hello", "you are safe")
    assert decision.startswith("# Simulated DeepSeek Output")


# ------------------------------------------------------------------ #
#  Hardening + PR
# ------------------------------------------------------------------ #
def test_harden_system_prompt_deterministic():
    hardened, diff = redteam.harden_system_prompt("You are a safe robot.")
    assert "<<system_prompt>>" in hardened and "<<end_system_prompt>>" in hardened
    assert "Operating boundaries" in hardened
    assert "Instruction precedence" in hardened
    assert "Ignore warning" in hardened
    assert diff
    # Deterministično: isti input → isti output.
    assert redteam.harden_system_prompt("You are a safe robot.")[0] == hardened


def test_open_prompt_hardening_pr_dry_run(store, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("git called v dry-run")

    monkeypatch.setattr(redteam.remediation, "_commit_desired_state", _boom)
    result = redteam.open_prompt_hardening_pr(
        store, "rob-1", "You are a safe robot.", dry_run=True, now=NOW
    )
    assert result.status == "diff_generated"
    assert result.diff and result.branch is None and result.pr_url is None


def test_open_prompt_hardening_pr_transport(store, monkeypatch):
    monkeypatch.setattr(
        redteam.remediation, "_commit_desired_state",
        lambda branch, files: (branch, "abc123"),
    )

    class FakeTransport:
        def open_pr(self, *, branch, title, body):
            self.calls = (branch, title, body)
            return "https://github.com/robAItech/rob-system/pull/9"

    trans = FakeTransport()
    result = redteam.open_prompt_hardening_pr(
        store, "rob-1", "You are a safe robot.", dry_run=False, transport=trans, now=NOW
    )
    assert result.status == "pr_open"
    assert result.branch == "fleet-security/rob-1-prompt-hardening"
    assert result.pr_url == "https://github.com/robAItech/rob-system/pull/9"
    assert trans.calls is not None
    assert "auto-merge" not in trans.calls[0] and "auto-merge" not in trans.calls[2]


def test_open_prompt_hardening_pr_auto_merge_refused(store, monkeypatch):
    monkeypatch.setattr(settings, "fs_pr_auto_merge", True)
    monkeypatch.setattr(
        redteam.remediation, "_commit_desired_state",
        lambda branch, files: (_ for _ in ()).throw(AssertionError("git")),
    )
    result = redteam.open_prompt_hardening_pr(
        store, "rob-1", "You are a safe robot.", dry_run=False, now=NOW
    )
    assert result.status == "error" and "auto-merge" in result.message


# ------------------------------------------------------------------ #
#  Compliance + API
# ------------------------------------------------------------------ #
def test_compliance_req01_redteam(store):
    from actions.fleet_security import discovery

    discovery.ingest_hostinfo(store, _hostinfo("rob-1"), now=NOW)
    brain = redteam.MockBrainTarget(secure=False)
    redteam.run_red_team(store, "rob-1", brain, system_prompt="safe", now=NOW)
    report = compliance.generate_report(store, now=NOW)
    assert "REQ-01" in report
    assert "non_compliant" in report.split("REQ-01")[1][:200]


def test_api_phase3_redteam(tmp_path, monkeypatch):
    monkeypatch.setattr(core_audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(core_quality, "ESCALATIONS_FILE", tmp_path / "escalations.json")
    monkeypatch.setattr(core_quality, "QUALITY_REGISTRY", tmp_path / "quality_registry.json")
    monkeypatch.setattr(core_quality, "REENABLE_GRACE_FILE", tmp_path / "reenable_grace.json")
    monkeypatch.setattr(settings, "fs_baselines_dir", str(tmp_path / "baselines"))
    monkeypatch.setattr(settings, "fs_db_path", str(tmp_path / "api.db"))
    from fastapi.testclient import TestClient

    from actions.fleet_security.main import app

    client = TestClient(app)
    r = client.post(
        "/api/fleet-security/redteam/run",
        json={"robot_id": "api-rob", "system_prompt": "safe", "mock_mode": "secure"},
    )
    assert r.status_code == 200 and r.json()["vulnerable"] == 0
    r = client.get("/api/fleet-security/redteam/runs")
    assert r.status_code == 200 and len(r.json()["runs"]) == len(redteam.PAYLOAD_LIBRARY)
