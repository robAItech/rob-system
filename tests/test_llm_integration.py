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
    client = DeepSeekLLMClient()
    res = await client.generate_completion(prompt="Izdelaj testno funkcijo", use_coder_model=True)
    assert len(res) > 0
    assert "Simulated DeepSeek Output" in res or "def" in res
