import pytest
from fastapi.testclient import TestClient
from actions.enterprise_auth_vault.main import app, vault
from actions.enterprise_auth_vault.enterprise_auth_vault import EnterpriseAuthVault
from actions.enterprise_auth_vault.schemas import Role, ApiKeyCreate

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_vault():
    vault.active_keys.clear()

def test_auth_vault_logic_and_rbac():
    v = EnterpriseAuthVault()
    
    # Issue Dev Key
    dev_key_resp = v.generate_api_key(ApiKeyCreate(client_id="dev_user", role=Role.DEVELOPER))
    key = dev_key_resp.api_key

    # Dev key passes READ_ONLY and DEVELOPER checks
    ok1, code1, _ = v.verify_api_key(key, Role.READ_ONLY)
    assert ok1 is True
    
    ok2, code2, _ = v.verify_api_key(key, Role.DEVELOPER)
    assert ok2 is True

    # Dev key fails ADMIN check
    ok3, code3, _ = v.verify_api_key(key, Role.ADMIN)
    assert ok3 is False
    assert code3 == "FORBIDDEN"

def test_encryption_roundtrip():
    v = EnterpriseAuthVault()
    secret = "TopSecretPassword123!"
    cipher = v.encrypt_data(secret)
    assert cipher.startswith("enc_v1:")
    
    decrypted = v.decrypt_data(cipher)
    assert decrypted == secret

    # Tampered cipher fails
    assert v.decrypt_data(cipher + "bad") is None

def test_fastapi_auth_vault_endpoints():
    # Issue key via API
    res = client.post("/keys/issue", json={"client_id": "test_client", "role": "ADMIN", "ttl_days": 10})
    assert res.status_code == 200
    api_key = res.json()["api_key"]

    # Verify key via API
    res_verify = client.post("/keys/verify", json={"api_key": api_key, "required_role": "ADMIN"})
    assert res_verify.status_code == 200

    # Encrypt/Decrypt via API
    res_enc = client.post("/vault/encrypt", json={"plain_text": "data"})
    assert res_enc.status_code == 200
    cipher = res_enc.json()["cipher_text"]

    res_dec = client.post("/vault/decrypt", json={"cipher_text": cipher})
    assert res_dec.status_code == 200
    assert res_dec.json()["plain_text"] == "data"
