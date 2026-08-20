import pytest
from fastapi.testclient import TestClient
from actions.audit_trail.main import app, audit_trail
from actions.audit_trail.schemas import AuditRecordCreate

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_audit_chain():
    audit_trail.chain.clear()

@pytest.mark.asyncio
async def test_cryptographic_chaining_and_tamper_detection():
    # 1. Ustvarimo 3 legalne zapise
    await audit_trail.record_event(AuditRecordCreate(actor="admin", action="CREATE_USER", target="user_123"))
    await audit_trail.record_event(AuditRecordCreate(actor="user_123", action="LOGIN", target="auth_sys"))
    await audit_trail.record_event(AuditRecordCreate(actor="admin", action="DELETE_USER", target="user_123"))

    assert len(audit_trail.chain) == 3

    # 2. Preverimo integriteto (Mora biti VALID)
    verification_ok = await audit_trail.verify_chain()
    assert verification_ok.is_valid is True
    assert verification_ok.total_records == 3

    # 3. SIMULACIJA HAKERSKEGA VDORA: Spremenimo podatke v preteklem logu
    # Spremenimo target v drugem zapisu, ne da bi preračunali hashe
    audit_trail.chain[1].target = "auth_bypassed"

    # 4. Ponovno preverimo integriteto (Mora biti INVALID)
    verification_tampered = await audit_trail.verify_chain()
    assert verification_tampered.is_valid is False
    assert verification_tampered.broken_at_id == "evt_audit_2"
    assert "Data tampered" in verification_tampered.reason

def test_fastapi_audit_endpoints():
    # Zapis
    res_post = client.post("/audit", json={
        "actor": "sys_service",
        "action": "DB_MIGRATION",
        "target": "db_main",
        "payload": {"version": "v1.2"}
    })
    assert res_post.status_code == 201
    assert res_post.json()["hash"] is not None

    # Branje
    res_get = client.get("/audit")
    assert res_get.status_code == 200
    assert len(res_get.json()) == 1

    # Verifikacija
    res_verify = client.get("/audit/verify")
    assert res_verify.status_code == 200
    assert res_verify.json()["is_valid"] is True
