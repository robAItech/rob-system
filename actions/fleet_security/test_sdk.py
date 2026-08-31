"""fleet_security — OEM embed SDK testi (offline).

SDK (Skin B) je dependency-free (stdlib). Testi: fingerprint strict shape +
determinizem, ASGI round-trip (payload → strict schema → 201), _post
failure → {"ok": False} (nikoli ne pade).
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
from actions.fleet_security import sdk  # noqa: E402
from actions.fleet_security.schemas import HostInfo  # noqa: E402
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

NOW = 1_700_000_000


def test_sdk_fingerprint_shape_strict():
    fp = sdk.fingerprint(
        device_id="dev-sdk", role="worker", hostname="h1",
        os_name="Linux", os_version="5.15", os_kernel="5.15.0",
        firmware={"motor": "1.0"},
        model={"name": "m", "version": "1", "provider": "oem", "sha256": "abc"},
        config={"k": 1}, collected_at=NOW,
    )
    parsed = HostInfo.model_validate(fp)  # strict, extra="forbid" → vrže ob ekstra
    assert parsed.device_id == "dev-sdk"
    assert parsed.model is not None and parsed.model.sha256 == "abc"
    assert parsed.model_dump() == fp  # round-trip: nobenih extra ključev


def test_sdk_fingerprint_deterministic(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.release", lambda: "5.15.0")
    monkeypatch.setattr("platform.version", lambda: "#1 SMP")
    monkeypatch.setattr("socket.gethostname", lambda: "rob-1")
    monkeypatch.setattr("uuid.getnode", lambda: 0xABCDEF123456)
    a = sdk.fingerprint()
    b = sdk.fingerprint()
    assert a == b
    assert a["device_id"] == "rob-abcdef123456"
    assert a["os"]["name"] == "linux"


def test_sdk_report_roundtrip_via_asgi(tmp_path, monkeypatch):
    monkeypatch.setattr(core_audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(core_quality, "ESCALATIONS_FILE", tmp_path / "escalations.json")
    monkeypatch.setattr(core_quality, "QUALITY_REGISTRY", tmp_path / "quality_registry.json")
    monkeypatch.setattr(core_quality, "REENABLE_GRACE_FILE", tmp_path / "reenable_grace.json")
    monkeypatch.setattr(settings, "fs_baselines_dir", str(tmp_path / "baselines"))
    monkeypatch.setattr(settings, "fs_db_path", str(tmp_path / "api.db"))

    from fastapi.testclient import TestClient
    from urllib.parse import urlparse

    from actions.fleet_security.main import app

    client = TestClient(app)

    def fake_post(url, payload, token=None, timeout=5.0):
        path = urlparse(url).path
        r = client.post(path, json=payload)
        return {"ok": r.status_code < 300, "status": r.status_code, "data": r.json()}

    monkeypatch.setattr(sdk, "_post", fake_post)

    res = sdk.report_hostinfo(
        "http://127.0.0.1:8000", hostinfo=sdk.fingerprint(device_id="sdk-1")
    )
    assert res["ok"] and res["status"] == 201
    res = sdk.report_telemetry("http://127.0.0.1:8000", "sdk-1", {"cpu_pct": 42.0})
    assert res["ok"] and res["status"] == 201
    res = sdk.report_network(
        "http://127.0.0.1:8000", "sdk-1",
        dst_host="10.0.0.9", dst_ip="10.0.0.9", dst_port=443, proto="tcp",
    )
    assert res["ok"] and res["status"] == 201

    store = FleetSecurityStore(tmp_path / "api.db")
    assert store.get_device("sdk-1") is not None
    assert len(store.recent_telemetry("sdk-1", n=10)) == 1
    assert len(store.recent_network_events("sdk-1")) == 1


def test_sdk_post_failure_returns_ok_false(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    res = sdk._post("http://127.0.0.1:1/api/x", {"a": 1})
    assert res["ok"] is False
    assert "error" in res
