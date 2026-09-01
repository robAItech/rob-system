"""fleet_security_sdk — paketni testi (offline, stdlib only)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repo root na path (za HostInfo v fingerprint-shape testu).
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from fleet_security_sdk import client as c  # noqa: E402
from fleet_security_sdk import FleetSecurityClient, fingerprint  # noqa: E402


# ------------------------------------------------------------------ #
#  Fingerprint
# ------------------------------------------------------------------ #
def test_fingerprint_shape_strict():
    from actions.fleet_security.schemas import HostInfo

    fp = fingerprint(
        device_id="dev-sdk", role="worker", hostname="h1",
        os_name="Linux", os_version="5.15", os_kernel="5.15.0",
        firmware={"motor": "1.0"},
        model={"name": "m", "version": "1", "provider": "oem", "sha256": "abc"},
        config={"k": 1}, collected_at=100,
    )
    parsed = HostInfo.model_validate(fp)  # strict, extra="forbid" → vrže ob ekstra
    assert parsed.device_id == "dev-sdk"
    assert parsed.model_dump() == fp


def test_fingerprint_deterministic(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.release", lambda: "5.15.0")
    monkeypatch.setattr("platform.version", lambda: "#1 SMP")
    monkeypatch.setattr("socket.gethostname", lambda: "rob-1")
    monkeypatch.setattr("uuid.getnode", lambda: 0xABCDEF123456)
    a = fingerprint()
    b = fingerprint()
    assert a == b
    assert a["device_id"] == "rob-abcdef123456"


# ------------------------------------------------------------------ #
#  Transport
# ------------------------------------------------------------------ #
def test_post_failure_ok_false(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    res = c._post("http://127.0.0.1:1/api/x", {"a": 1})
    assert res["ok"] is False and "error" in res


# ------------------------------------------------------------------ #
#  FleetSecurityClient
# ------------------------------------------------------------------ #
def _capture(monkeypatch):
    calls: dict = {}

    def fake_post(url, payload, token=None, timeout=5.0):
        calls["url"] = url
        calls["payload"] = payload
        calls["token"] = token
        return {"ok": True, "status": 201, "data": {}}

    monkeypatch.setattr(c, "_post", fake_post)
    return calls


def test_client_report_hostinfo_payload_url(monkeypatch):
    calls = _capture(monkeypatch)
    cli = FleetSecurityClient("http://host:8000", token="t", device_id="dev-1")
    hi = {"device_id": "dev-1", "hostname": "h", "role": "worker",
          "os": {"name": "linux", "version": "1", "kernel": "1"},
          "firmware": [], "model": None, "config": {}, "source": "sdk", "collected_at": None}
    cli.report_hostinfo(hostinfo=hi)
    assert calls["url"].endswith("/api/fleet-security/devices/ingest")
    assert calls["payload"]["device_id"] == "dev-1"
    assert calls["token"] == "t"


def test_client_report_telemetry(monkeypatch):
    calls = _capture(monkeypatch)
    cli = FleetSecurityClient("http://host:8000", device_id="dev-1")
    cli.report_telemetry({"cpu_pct": 42.0}, ts=100)
    assert calls["url"].endswith("/api/fleet-security/monitor/telemetry")
    assert calls["payload"]["device_id"] == "dev-1"
    assert calls["payload"]["metrics"] == {"cpu_pct": 42.0}
    assert calls["payload"]["ts"] == 100


def test_client_report_network(monkeypatch):
    calls = _capture(monkeypatch)
    cli = FleetSecurityClient("http://host:8000", device_id="dev-1")
    cli.report_network(dst_ip="10.0.0.9", dst_port=443, proto="tcp")
    assert calls["url"].endswith("/api/fleet-security/monitor/network")
    assert calls["payload"]["dst_ip"] == "10.0.0.9"
    assert calls["payload"]["dst_port"] == 443


def test_client_report_model(monkeypatch):
    calls = _capture(monkeypatch)
    cli = FleetSecurityClient("http://host:8000", device_id="dev-1")
    cli.report_model("vision-model", "2.0", sha256="a" * 64, provider="oem",
                     pushed_by="ci", repo_url="r")
    assert calls["url"].endswith("/api/fleet-security/supplychain/record")
    assert calls["payload"]["device_id"] == "dev-1"
    assert calls["payload"]["model"] == {
        "name": "vision-model", "version": "2.0", "provider": "oem", "sha256": "a" * 64,
    }
    assert calls["payload"]["pushed_by"] == "ci"
    assert calls["payload"]["repo_url"] == "r"


def test_client_device_id_auto(monkeypatch):
    monkeypatch.setattr("uuid.getnode", lambda: 0xABCDEF123456)
    monkeypatch.setattr("socket.gethostname", lambda: "h")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.release", lambda: "1")
    monkeypatch.setattr("platform.version", lambda: "1")
    cli = FleetSecurityClient("http://host:8000")  # ni device_id
    assert cli._did() == "rob-abcdef123456"
