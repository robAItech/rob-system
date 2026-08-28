"""Pytest test suite za actions/identity_federation_router.

Deterministično, brez omrežja. Preveri: IdP registracijo, PKCE (authorize URL +
code exchange s preverbo verifierja), client-credentials grant, device flow,
JWT ustvarjanje/validacijo in FastAPI plast.
"""

import pytest
from fastapi.testclient import TestClient

from actions.identity_federation_router.federation import (
    FederationError,
    IdPConfig,
    IdentityFederationRouter,
    create_jwt,
    validate_jwt,
)
from actions.identity_federation_router.main import app, router


@pytest.fixture(autouse=True)
def _fresh_router():
    router.idps.clear()
    router._pending_codes.clear()
    router._pending_device.clear()
    router.register_idp(
        IdPConfig(
            name="okta", issuer="https://okta.example.com", token_url="https://okta.example.com/token",
            client_id="client-1", client_secret="super-secret", jwks_uri="https://okta.example.com/jwks",
        )
    )
    yield


def _new_router() -> IdentityFederationRouter:
    r = IdentityFederationRouter()
    r.register_idp(
        IdPConfig(name="okta", issuer="https://okta.example.com",
                  token_url="https://okta.example.com/token", client_id="c1", client_secret="s3cret")
    )
    return r


# ── Registracija ────────────────────────────────────────────────────────────
def test_register_and_get_idp():
    r = _new_router()
    assert r.get_idp("okta").issuer == "https://okta.example.com"
    with pytest.raises(FederationError):
        r.get_idp("unknown")


# ── PKCE ────────────────────────────────────────────────────────────────────
def test_pkce_authorize_url():
    r = _new_router()
    verifier, challenge = r.new_pkce_pair()
    url = r.authorization_code_url("okta", "https://app.example/cb", "state1", challenge)
    assert "https://okta.example.com/authorize" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "state=state1" in url


def test_pkce_exchange_requires_matching_verifier():
    r = _new_router()
    verifier, challenge = r.new_pkce_pair()
    r.store_code("okta", "code-1", challenge, "https://app.example/cb", "user-42")

    ctx = r.exchange_code("okta", "code-1", verifier, "https://app.example/cb")
    assert ctx.subject == "user-42"
    assert ctx.idp == "okta"
    assert ctx.raw_token  # izdan JWT

    # Napačen verifier → zavrnjeno.
    r.store_code("okta", "code-2", challenge, "https://app.example/cb", "u")
    with pytest.raises(FederationError):
        r.exchange_code("okta", "code-2", "wrong-verifier", "https://app.example/cb")


# ── Client credentials ──────────────────────────────────────────────────────
def test_client_credentials_flow():
    r = _new_router()
    ctx = r.client_credentials_flow("okta", scope=["api", "billing"])
    assert ctx.subject == "client:c1"
    assert ctx.scopes == ["api", "billing"]


# ── Device flow ─────────────────────────────────────────────────────────────
def test_device_flow_pending_then_approved():
    r = _new_router()
    start = r.device_flow_start("okta")
    assert start["device_code"] and start["user_code"]

    with pytest.raises(FederationError):
        r.device_flow_poll("okta", start["device_code"])  # ni odobren → pending

    assert r.device_flow_approve(start["device_code"]) is True
    ctx = r.device_flow_poll("okta", start["device_code"])
    assert ctx.subject == "device-user"


# ── JWT ─────────────────────────────────────────────────────────────────────
def test_jwt_roundtrip_and_validation():
    secret = "s3cret"
    token = create_jwt(secret, {"iss": "https://okta.example.com", "sub": "u1"})
    payload = validate_jwt(secret, token, issuer="https://okta.example.com")
    assert payload["sub"] == "u1"

    with pytest.raises(FederationError):
        validate_jwt("wrong-secret", token, issuer="https://okta.example.com")

    with pytest.raises(FederationError):
        validate_jwt(secret, token, issuer="https://other.example.com")


def test_router_validate_rejects_tampered():
    r = _new_router()
    ctx = r.client_credentials_flow("okta")
    tampered = ctx.raw_token[:-2] + ("ab" if not ctx.raw_token.endswith("ab") else "cd")
    with pytest.raises(FederationError):
        r.validate("okta", tampered)


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_flows():
    client = TestClient(app)

    # Authorize URL.
    r = client.post("/authorize-url", json={
        "idp": "okta", "redirect_uri": "https://app.example/cb", "state": "s", "code_challenge": "ch",
    })
    assert r.status_code == 200
    assert r.json()["authorization_url"].startswith("https://okta.example.com/authorize")

    # Client credentials → token.
    r2 = client.post("/token", json={"idp": "okta", "grant_type": "client_credentials", "scope": ["api"]})
    assert r2.status_code == 200
    token = r2.json()["raw_token"]
    assert r2.json()["subject"].startswith("client:")

    # Validate JWT.
    r3 = client.post("/validate-jwt", json={"idp": "okta", "token": token})
    assert r3.json()["valid"] is True

    # Health.
    assert client.get("/health").json()["status"] == "UP"
