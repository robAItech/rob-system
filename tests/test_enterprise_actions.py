"""tests/test_enterprise_actions.py — integracijski testi novih enterprise Actions.

Nova Actions iz arhitekturne revizije: webhook_dispatcher, api_version_manager,
secret_rotation + absorbcije (rate_limiter token_bucket strategija, currency
InvertRateSanitizer, report_builder markdown adapter). Brez omrežja — transport
in čas sta injicirana tam, kjer je treba.
"""

import pytest
from fastapi.testclient import TestClient

# ── Absorbcija: token_bucket → rate_limiter strategija ──────────────────────
from actions.rate_limiter.rate_limiter import RateLimiter, TokenBucket
from actions.rate_limiter.schemas import RateLimitConfig


def test_token_bucket_absorbed_as_rate_limiter_strategy():
    limiter = RateLimiter(RateLimitConfig(max_requests=2, window_seconds=10.0, strategy="token_bucket"))
    assert limiter.is_allowed("k") == (True, 1, 0.0)
    assert limiter.is_allowed("k") == (True, 0, 0.0)
    ok, remaining, reset = limiter.is_allowed("k")
    assert (ok, remaining, reset) == (False, 0, 10.0)
    # Algoritem je dostopen tudi neposredno (nekdanji actions.token_bucket).
    assert TokenBucket(capacity=1, rate=1.0).allow() is True


# ── Absorbcija: fix_currency_inverted_rate → InvertRateSanitizer ────────────
from actions.currency_converter.currency_converter import InvertRateSanitizer, InvertedRateError


def test_inverted_rate_sanitizer_catches_reciprocal():
    with pytest.raises(InvertedRateError):
        InvertRateSanitizer().sanitize({"EUR": "1.18"})  # reciprok od 0.85


# ── Konsolidacija: markdown_summary → report_builder adapter ────────────────
from actions.report_builder.report_builder import build_report_markdown
from actions.report_builder.markdown import render_markdown
from actions.report_builder.schemas import SummaryDocument


def test_markdown_adapter_in_report_builder():
    md = build_report_markdown("naslov,opis\nSekcija,vsebina\n", title="Raport")
    assert md.startswith("# Raport")
    assert "## sekcija" in md
    doc = SummaryDocument(title="T", paragraphs=["A"], bullet_points=["1", "2", "3"])
    assert render_markdown(doc).startswith("# T")


# ── Nova Action: webhook_dispatcher (FastAPI) ───────────────────────────────
from actions.webhook_dispatcher.main import app as webhook_app


def test_webhook_dispatcher_registers_and_health():
    with TestClient(webhook_app) as client:
        r = client.post("/subscribers", json={
            "url": "https://hooks.example.com/rob", "secret": "secret123", "events": ["invoice.paid"],
        })
        assert r.status_code == 200
        assert r.json()["active"] is True
        # Secret se nikoli ne razkrije v odgovoru.
        assert "secret" not in r.json()

        h = client.get("/health")
        assert h.status_code == 200
        assert h.json()["status"] == "UP"
        assert h.json()["subscribers"] >= 1


def test_webhook_dispatcher_rejects_bad_url_scheme():
    with TestClient(webhook_app) as client:
        r = client.post("/subscribers", json={"url": "file:///etc/passwd", "secret": "secret123"})
        assert r.status_code == 422


# ── Nova Action: api_version_manager (FastAPI) ──────────────────────────────
from actions.api_version_manager.main import app as version_app


def test_api_version_manager_register_route_bc():
    with TestClient(version_app) as client:
        assert client.post("/versions", json={
            "tag": "v1", "version": {"major": 1, "minor": 0, "patch": 0}, "weight": 100,
        }).status_code == 200

        r = client.post("/route", json={"versions": [{"tag": "v1", "weight": 100}]})
        assert r.status_code == 200
        assert r.json()["selected"] == "v1"

        # Aditivna sprememba sheme ni prelomna.
        r2 = client.post("/check-bc", json={
            "old_schema": {"properties": {"id": {"type": "integer"}}, "required": ["id"]},
            "new_schema": {"properties": {"id": {"type": "integer"}, "x": {"type": "string"}}, "required": ["id"]},
        })
        assert r2.json()["is_breaking"] is False


# ── Nova Action: secret_rotation (FastAPI) ──────────────────────────────────
from actions.secret_rotation.main import app as rotation_app


def test_secret_rotation_register_status_rotate_activate():
    with TestClient(rotation_app) as client:
        r = client.post("/secrets", json={"name": "db_pass", "kind": "db_password", "rotation_interval_days": 30})
        assert r.status_code == 200
        body = r.json()
        assert body["phase"] == "active"
        assert body["active_value_masked"].endswith("…")

        # Rotacija: nova vrednost → staged; nato aktivacija → aktivna (double buffer).
        assert client.post("/rotate", json={"name": "db_pass"}).json()["action"] == "rotated"
        act = client.post("/activate", json={"name": "db_pass"}).json()
        assert act["action"] == "activated"

        audit = client.get("/audit")
        actions = [e["action"] for e in audit.json()]
        assert actions == ["register", "rotate", "activate"]


def test_secret_rotation_revoke_and_due():
    with TestClient(rotation_app) as client:
        client.post("/secrets", json={"name": "tmp_key", "kind": "api_key", "rotation_interval_days": 30})
        assert client.get("/due").json() == []
        rv = client.post("/revoke", json={"name": "tmp_key", "reason": "test"})
        assert rv.json()["revoked"] is True
        # Umaknjena skrivnost ni več rotirljiva.
        assert client.post("/rotate", json={"name": "tmp_key"}).status_code == 404
