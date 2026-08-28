"""Pytest test suite za actions/pii_masking_sanitizer.

Deterministično. Preveri: registracijo polj (ročno + dekorator), maskiranje
po strategijah, deterministično tokenizacijo, redakcijo besedila in FastAPI.
"""

import pytest
from fastapi.testclient import TestClient

from actions.pii_masking_sanitizer.main import app, masker
from actions.pii_masking_sanitizer.pii import PII, PIIMasker


@pytest.fixture(autouse=True)
def _fresh_masker():
    masker.fields.clear()
    yield


# ── Registracija ────────────────────────────────────────────────────────────
def test_register_field_manual():
    m = PIIMasker()
    m.register_field("email", "email", "partial")
    assert "email" in m.fields
    assert m.fields["email"].category == "email"


def test_register_field_invalid_strategy():
    m = PIIMasker()
    with pytest.raises(ValueError):
        m.register_field("x", "y", "bogus")


# ── Dekorator ───────────────────────────────────────────────────────────────
def test_register_schema_from_decorator():
    class User:
        name: str = "Ana"
        email = PII("email", strategy="partial")
        iban = PII("iban", strategy="mask")

    m = PIIMasker()
    registered = m.register_schema(User)
    assert {f.name for f in registered} == {"email", "iban"}


# ── Maskiranje ──────────────────────────────────────────────────────────────
def test_mask_partial():
    m = PIIMasker()
    m.register_field("email", "email", "partial")
    out = m.mask({"email": "ana@example.com", "name": "Ana"})
    assert out["email"] == "an***om"  # prvi 2 + *** + zadnja 2
    assert out["name"] == "Ana"       # neregistrirano ostane


def test_mask_full():
    m = PIIMasker()
    m.register_field("ssn", "ssn", "mask")
    assert m.mask({"ssn": "123-45-6789"}) == {"ssn": "***"}


def test_mask_nested():
    m = PIIMasker()
    m.register_field("email", "email", "mask")
    out = m.mask({"user": {"email": "a@b.c", "items": [{"email": "d@e.f"}]}})
    assert out["user"]["email"] == "***"
    assert out["user"]["items"][0]["email"] == "***"


# ── Tokenizacija ────────────────────────────────────────────────────────────
def test_tokenize_deterministic():
    m = PIIMasker(secret="secret-1")
    t1 = m.tokenize("ana@example.com", "email")
    t2 = m.tokenize("ana@example.com", "email")
    assert t1 == t2
    assert t1.startswith("tok_")
    # Druga vrednost ali secret → drug token.
    assert m.tokenize("bob@example.com", "email") != t1


# ── Redakcija besedila ──────────────────────────────────────────────────────
def test_redact_text():
    m = PIIMasker()
    text = "Kontakt: ana@example.com, tel +386 40 123 456, IBAN SI56 1234 5678 9012 345"
    redacted = m.redact_text(text)
    assert "ana@example.com" not in redacted
    assert "[email-REDACTED]" in redacted
    assert "[iban-REDACTED]" in redacted


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_mask_redact_health():
    client = TestClient(app)
    # Registriraj email prek API-ja (test /fields) — fixture je izpraznil privzete.
    assert client.post("/fields", json={"name": "email", "category": "email", "strategy": "partial"}).status_code == 200
    r = client.post("/mask", json={"data": {"email": "ana@example.com", "name": "Ana"}})
    assert r.status_code == 200
    assert r.json()["masked"]["email"] != "ana@example.com"
    assert r.json()["masked"]["name"] == "Ana"

    r2 = client.post("/redact", json={"text": "piši na ana@example.com"})
    assert "[email-REDACTED]" in r2.json()["redacted"]

    h = client.get("/health")
    assert h.json()["status"] == "UP"
