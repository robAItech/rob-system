"""Pytest test suite for the slugify module (directive: 100% green)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make the package importable regardless of how pytest discovers this file.
ROOT = Path(__file__).resolve().parents[1]  # actions/ (parent of actions/slugify)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from slugify import app, router, slug, slug_async  # noqa: E402
from slugify.schemas import SlugifyRequest, SlugifyResponse  # noqa: E402

client = TestClient(app)


# --------------------------------------------------------------------------
# Core slug() unit tests — edge cases and the directive rules
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # lowercase
        ("HELLO", "hello"),
        ("Hello World", "hello-world"),
        # spaces -> hyphens
        ("Hello   World", "hello-world"),
        ("  Multiple   Spaces  ", "multiple-spaces"),
        ("a b c", "a-b-c"),
        # special characters removed
        ("Hello, World!", "hello-world"),
        ("Hello.World", "hello-world"),
        ("hello_world", "hello-world"),
        ("Version 2.0", "version-2-0"),
        # hyphen handling
        ("a--b", "a-b"),
        ("a - b", "a-b"),
        ("-leading", "leading"),
        ("trailing-", "trailing"),
        ("---", ""),
        # empty / whitespace-only
        ("", ""),
        ("   ", ""),
        # already slugged
        ("already-slugged", "already-slugged"),
        # unicode transliteration
        ("Café", "cafe"),
        ("Äpfel", "apfel"),
    ],
)
def test_slug_basic(text: str, expected: str) -> None:
    assert slug(text) == expected


def test_slug_rejects_non_string() -> None:
    with pytest.raises(TypeError):
        slug(None)
    with pytest.raises(TypeError):
        slug(123)
    with pytest.raises(TypeError):
        slug(["hello"])


def test_slugify_alias() -> None:
    from slugify import slugify as alias

    assert alias("Hello World") == "hello-world"


@pytest.mark.asyncio
async def test_slug_async() -> None:
    assert await slug_async("Hello World") == "hello-world"
    assert await slug_async("") == ""


# --------------------------------------------------------------------------
# Pydantic V2 schemas — strict validators
# --------------------------------------------------------------------------
def test_request_schema_valid() -> None:
    req = SlugifyRequest(text="Hello World")
    assert req.text == "Hello World"


def test_request_schema_strict_rejects_non_string() -> None:
    with pytest.raises(Exception):
        SlugifyRequest(text=123)
    with pytest.raises(Exception):
        SlugifyRequest(text=None)


def test_request_schema_forbids_extra_fields() -> None:
    with pytest.raises(Exception):
        SlugifyRequest(text="hi", extra="x")


def test_response_schema() -> None:
    resp = SlugifyResponse(slug="hello-world")
    assert resp.slug == "hello-world"


# --------------------------------------------------------------------------
# FastAPI — direct JSONResponse 4xx/5xx handling
# --------------------------------------------------------------------------
def test_post_slugify_ok() -> None:
    resp = client.post("/slugify", json={"text": "Hello World!"})
    assert resp.status_code == 200
    assert resp.json() == {"slug": "hello-world"}


def test_post_slugify_empty_string() -> None:
    resp = client.post("/slugify", json={"text": ""})
    assert resp.status_code == 200
    assert resp.json() == {"slug": ""}


def test_post_slugify_invalid_type_returns_4xx() -> None:
    resp = client.post("/slugify", json={"text": 123})
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_post_slugify_missing_field_returns_4xx() -> None:
    resp = client.post("/slugify", json={})
    assert resp.status_code == 422
    assert "detail" in resp.json()


def test_post_slugify_extra_field_returns_4xx() -> None:
    resp = client.post("/slugify", json={"text": "hi", "nope": 1})
    assert resp.status_code == 422


def test_get_slugify_query_param() -> None:
    resp = client.get("/slugify", params={"text": "Hello World"})
    assert resp.status_code == 200
    assert resp.json() == {"slug": "hello-world"}


def test_get_slugify_missing_query_returns_4xx() -> None:
    resp = client.get("/slugify")
    assert resp.status_code == 422


def test_post_root_alias() -> None:
    resp = client.post("/", json={"text": "Hello World"})
    assert resp.status_code == 200
    assert resp.json() == {"slug": "hello-world"}


def test_router_prefix() -> None:
    assert router.prefix == "/slugify"


def test_unknown_path_returns_404() -> None:
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404


def test_internal_error_returns_direct_jsonresponse_500(monkeypatch) -> None:
    import slugify.main as main_module

    def boom(text: str) -> str:  # pragma: no cover - forced failure
        raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "slug", boom)
    resp = client.post("/slugify", json={"text": "x"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "internal server error"}
