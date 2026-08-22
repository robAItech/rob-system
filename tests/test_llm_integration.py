import pytest
import asyncio
from pathlib import Path
from core.config import settings
from core.llm_client import DeepSeekLLMClient

def test_dotenv_loading():
    assert Path(".env").exists()
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_model_chat == "deepseek-v4-flash"
    assert settings.deepseek_model_coder == "deepseek-v4-flash"

def test_llm_code_extraction():
    client = DeepSeekLLMClient()
    raw_response = "Tukaj je koda:\n```python\ndef hello():\n    return 'world'\n```"
    extracted = client.extract_code_block(raw_response)
    assert extracted == "def hello():\n    return 'world'"

@pytest.mark.asyncio
async def test_deepseek_fallback_completion():
    """generate_completion s coder modelom vrne vsebino — httpx mock-an.

    Prej je ta test klical PRAVI DeepSeek API in assertal na vsebino modelovega
    odgovora (`"def" in res`) — po naravi flaky (nedeterminističen izhod,
    omrežje, stroški na vsak `pytest tests/`). Zdaj je omrežje mock-an (enako
    kot `test_llm_client.py`), zato je determinističen in brez API-ja.
    """
    from unittest import mock
    from core.llm_client import DeepSeekLLMClient

    class _FakeResp:
        def __init__(self):
            self.status_code = 200
            self._data = {"choices": [{"message": {"content": "def hello():\n    return 'world'\n"}}]}

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    class _FakeAsyncClient:
        def __init__(self):
            self.posts = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            self.posts.append((a, k))
            return _FakeResp()

    fake = _FakeAsyncClient()
    client = DeepSeekLLMClient()
    with mock.patch("core.llm_client.httpx.AsyncClient", return_value=fake):
        res = await client.generate_completion(prompt="Izdelaj testno funkcijo", use_coder_model=True)
    assert "def hello():" in res
    # Uporabljen je coder model (fallback-path intent).
    payload = fake.posts[0][1].get("json", {})
    assert payload["model"] == settings.deepseek_model_coder
