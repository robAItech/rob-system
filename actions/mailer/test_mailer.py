import pytest
from fastapi.testclient import TestClient
from actions.mailer.main import app, mailer

client = TestClient(app)

@pytest.mark.asyncio
async def test_primary_and_fallback_logic():
    req = {"to_email": "test@example.com", "subject": "Hello", "body": "World"}
    
    # 1. Primary Success
    mailer.primary_fail_sim = False
    res1 = client.post("/send", json=req)
    assert res1.status_code == 200
    assert res1.json()["provider_used"] == "PRIMARY_SMTP"
    
    # 2. Fallback Success
    mailer.primary_fail_sim = True
    res2 = client.post("/send", json=req)
    assert res2.status_code == 200
    assert res2.json()["provider_used"] == "FALLBACK_API"
