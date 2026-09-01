"""nis2_compliance — testi API (child #3, D3, offline).

TestClient (starlette) poganja ASGI app sinhrono; per-firm DB in audit gresta
v ``tmp_path`` prek monkeypatch-a.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit as core_audit  # noqa: E402
from core.config import settings  # noqa: E402
from actions.nis2_compliance.main import app  # noqa: E402

NOW = 1_700_000_000


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Izoliran API: per-firm DB + audit v tmp_path."""
    monkeypatch.setattr(core_audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(settings, "nis2_db_root", str(tmp_path / "nis2"))
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def _firm_payload(**over) -> dict:
    base = {
        "naziv": "Acme d.o.o.",
        "sektor": "energetika",
        "zaposleni": 300,
        "promet_mio": 60.0,
        "kontakt": "direktor@acme.si",
        "answers": [
            {"question_id": "mfa_aktiviran", "answer": "da", "answered_at": NOW},
            {"question_id": "register_sredstev", "answer": "Inventar.xlsx", "answered_at": NOW},
        ],
    }
    base.update(over)
    return base


def _create_firm(client) -> dict:
    resp = client.post("/api/nis2-compliance/firms", json=_firm_payload())
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health(client):
    resp = client.get("/api/nis2-compliance/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_firm_returns_profile_and_scope(client):
    """AC7: POST /firms → 200 z profile + scope."""
    data = _create_firm(client)
    assert "firm_id" in data
    assert data["profile"]["naziv"] == "Acme d.o.o."
    assert data["profile"]["sektor"] == "energetika"
    assert data["scope"]["tier"] == "bistveni"  # zaposleni=300 ≥ 250
    assert data["evidence_count"] > 0


def test_get_firm_full_package(client):
    """AC7: GET /firms/{id} → 200 paket (profile + scope + policies + risk)."""
    firm_id = _create_firm(client)["firm_id"]
    resp = client.get(f"/api/nis2-compliance/firms/{firm_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["firm_id"] == firm_id
    assert data["profile"]["naziv"] == "Acme d.o.o."
    assert data["scope"]["tier"] == "bistveni"
    assert len(data["policies"]) == 7
    assert "{{" not in data["policies"][0]["body_markdown"]
    assert len(data["risk"]["items"]) > 0


def test_generate_policies(client):
    """AC7: POST /firms/{id}/policies → 200 list PolicyDoc."""
    firm_id = _create_firm(client)["firm_id"]
    resp = client.post(f"/api/nis2-compliance/firms/{firm_id}/policies")
    assert resp.status_code == 200, resp.text
    policies = resp.json()["policies"]
    assert len(policies) == 7
    assert all("{{" not in p["body_markdown"] for p in policies)


def test_assess_risk(client):
    """AC7: POST /firms/{id}/risk → 200 RiskRegister."""
    firm_id = _create_firm(client)["firm_id"]
    resp = client.post(f"/api/nis2-compliance/firms/{firm_id}/risk")
    assert resp.status_code == 200, resp.text
    register = resp.json()
    assert register["firm_id"] == firm_id
    assert len(register["items"]) > 0
    item = register["items"][0]
    assert item["score"] == item["likelihood"] * item["impact"]


def test_unknown_firm_404(client):
    """AC7: neznana firma → 404."""
    resp = client.get("/api/nis2-compliance/firms/ne-obstaja")
    assert resp.status_code == 404
    assert "ne obstaja" in resp.json()["error"]


def test_invalid_input_400(client):
    """AC7: negativen zaposleni → 400 (InvalidScopeInputError)."""
    payload = _firm_payload(zaposleni=-5)
    resp = client.post("/api/nis2-compliance/firms", json=payload)
    assert resp.status_code == 400
    assert "negativen" in resp.json()["error"]


def test_audit_event_written(client):
    """AC8: vsak handler piše audit event nis2-compliance-http."""
    _create_firm(client)
    events = core_audit.query(event="nis2-compliance-http")
    assert len(events) >= 1
    assert events[0]["project"] == "/firms"


def test_audit_written_on_failure(client):
    """AC8: tudi napaka zapiše audit event (zero silent failures)."""
    client.get("/api/nis2-compliance/firms/ne-obstaja")
    events = core_audit.query(event="nis2-compliance-http")
    assert any(e["status"] == "failed" for e in events)


def test_runtime_visible_via_load_module_app():
    """AC10: core/actions_runtime.py naloži actions.nis2_compliance.main."""
    from core import actions_runtime
    from fastapi.testclient import TestClient

    sub = actions_runtime.load_module_app("nis2_compliance")
    assert sub is not None
    with TestClient(sub) as client:
        resp = client.get("/api/nis2-compliance/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_build_runtime_app_mounts_nis2():
    """AC10: build_runtime_app() mount-a nis2_compliance (runtime-viden)."""
    from core import actions_runtime
    from fastapi.testclient import TestClient

    app = actions_runtime.build_runtime_app(modules=["nis2_compliance"])
    with TestClient(app) as client:
        mods = client.get("/api/runtime/modules").json()
    mounted = {m["name"] for m in mods if m["mounted"]}
    assert "nis2_compliance" in mounted
