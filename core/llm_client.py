import json
import re
import httpx
from typing import Dict, Any, List, Optional
from core.config import settings

class DeepSeekLLMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.deepseek_api_key
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.timeout = settings.llm_timeout_seconds
        self.temperature = settings.llm_temperature

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def extract_code_block(self, text: str) -> str:
        """Ekstrahira kodo iz markdown blocov ali vrne surovo besedilo."""
        pattern = r"```(?:python)?\s*(.*?)\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    async def generate_completion(
        self, 
        prompt: str, 
        system_prompt: str = "Ti si avtonomni AI inženir v sistemu Rob AI Studio.", 
        use_coder_model: bool = True
    ) -> str:
        """Pošlje zahtevek na DeepSeek API z avtomatskim fallbackom."""
        if not settings.is_real_key_available():
            # Determinističen odziv za lokalno testiranje brez veljavnega API ključa
            return f"# Simulated DeepSeek Output for prompt: {prompt[:30]}...\n# Mode: Autopilot Green"

        model = settings.deepseek_model_coder if use_coder_model else settings.deepseek_model_chat
        endpoint = f"{self.base_url}/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "stream": False
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(endpoint, headers=self._get_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
