"""Testi za P1 — zanesljiv LLMClient (retry, model-fallback, guard).

Brez pravih HTTP klicev — httpx se mocka. Preveri: retry na 429/5xx,
model-fallback ob modelovem errorju (400/404/422), in da se max_tokens ne
doda ko config nima nastavljenega.
"""
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.llm_client import DeepSeekLLMClient


def _client(**over):
    c = DeepSeekLLMClient(api_key="sk-test", base_url="https://x")
    c.max_retries = 3
    c.backoff = 0.0  # brez čakanja v testu
    for k, v in over.items():
        setattr(c, k, v)
    return c


class _FakeResp:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {"choices": [{"message": {"content": "OK"}}]}

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        resp = self._responses.pop(0) if self._responses else _FakeResp(200)
        self.posts.append((a, k))
        # Simuliraj HTTPStatusError na status >= 400
        if resp.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                "err", request=httpx.Request("POST", "http://x"),
                response=httpx.Response(resp.status_code, request=httpx.Request("POST", "http://x")),
            )
        return resp


@pytest.mark.asyncio
async def test_retry_na_429_uspeh():
    """Prvi 429 → retry → drugi 200 → OK, 2 POST-a."""
    c = _client()
    fake = _FakeAsyncClient([_FakeResp(429), _FakeResp(200)])
    with mock.patch("core.llm_client.httpx.AsyncClient", return_value=fake):
        out = await c.generate_completion("hi")
    assert out == "OK"
    assert len(fake.posts) == 2


@pytest.mark.asyncio
async def test_model_fallback_na_400():
    """Coder 400 (modelov error) → fallback na chat, ne na retry istega."""
    c = _client()
    calls = []
    fake = _FakeAsyncClient([_FakeResp(400), _FakeResp(200)])
    with mock.patch("core.llm_client.httpx.AsyncClient", return_value=fake):
        out = await c.generate_completion("hi", use_coder_model=True)
    assert out == "OK"
    # Preveri, da sta bili izvedeni dve različni model zahtevki (coder → chat).
    payloads = [k.get("json", {}) for _, k in fake.posts]
    assert len(payloads) == 2
    assert payloads[0]["model"] != payloads[1]["model"]  # fallback na drug model


@pytest.mark.asyncio
async def test_odziv_ko_noben_retry_ne_uspe():
    """Vsi poskusi (coder 3×500 + chat 3×500 = 6) → RuntimeError."""
    c = _client()
    fake = _FakeAsyncClient([_FakeResp(500)] * 6)
    with mock.patch("core.llm_client.httpx.AsyncClient", return_value=fake):
        with pytest.raises(RuntimeError):
            await c.generate_completion("hi")


@pytest.mark.asyncio
async def test_max_tokens_se_doda_le_ko_config_nastavljen():
    """Guard: max_completion_tokens=None → max_tokens ni v payloadu."""
    c = _client(max_completion_tokens=None)
    fake = _FakeAsyncClient([_FakeResp(200)])
    with mock.patch("core.llm_client.httpx.AsyncClient", return_value=fake):
        await c.generate_completion("hi")
    payload = fake.posts[0][1].get("json", {})
    assert "max_tokens" not in payload

    c2 = _client(max_completion_tokens=128)
    fake2 = _FakeAsyncClient([_FakeResp(200)])
    with mock.patch("core.llm_client.httpx.AsyncClient", return_value=fake2):
        await c2.generate_completion("hi")
    payload2 = fake2.posts[0][1].get("json", {})
    assert payload2["max_tokens"] == 128
