import json
import re
import httpx
from typing import Dict, Any, List, Optional
from core.config import settings


def estimate_tokens(text: str) -> int:
    """Hevristika brez odvisnosti: ~4 znaki/token za mešano kodo + prozo.

    Uporablja se SAMO za log/meritve, nikoli za odločanje (odločitve so po znakih).
    """
    return max(1, (len(text) + 3) // 4)


class DeepSeekLLMClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.deepseek_api_key
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.timeout = settings.llm_timeout_seconds
        self.temperature = settings.llm_temperature
        # P1 — zanesljivost: retry/backoff + model-fallback + guard.
        self.max_retries = getattr(settings, "llm_max_retries", 3) or 3
        self.backoff = getattr(settings, "llm_backoff_seconds", 0.5) or 0.5
        self.max_completion_tokens = getattr(settings, "llm_max_completion_tokens", None) or None
        self.last_usage: Dict[str, Any] = {}   # Korak 3: usage iz zadnjega API odgovora

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

    async def _post_once(self, endpoint: str, headers: Dict[str, str], payload: Dict[str, Any]) -> str:
        """Ena POST + razreža vsebino, dviga error na ne-uspeh."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            self.last_usage = data.get("usage", {}) or {}   # Korak 3: token usage
            return data["choices"][0]["message"]["content"]

    async def _post_message(self, endpoint: str, headers: Dict[str, str], payload: Dict[str, Any]) -> Dict[str, Any]:
        """Ena POST, vrne message dict (content + tool_calls + reasoning_content)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            self.last_usage = data.get("usage", {}) or {}   # Korak 3: token usage
            return data["choices"][0]["message"]

    async def _complete_with(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
    ) -> str:
        """Pošlje zahtevek na določen model, dviga napako ob neuspehu."""
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "stream": False,
        }
        if self.max_completion_tokens:
            payload["max_tokens"] = self.max_completion_tokens
        return await self._post_once(endpoint, self._get_headers(), payload)

    async def _complete_with_tools_once(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str,
        model: str,
    ) -> Dict[str, Any]:
        """Pošlje zahtevek z orodji (function-calling), vrne message dict."""
        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "temperature": self.temperature,
            "stream": False,
        }
        if self.max_completion_tokens:
            payload["max_tokens"] = self.max_completion_tokens
        return await self._post_message(endpoint, self._get_headers(), payload)

    async def _retry_models(self, use_coder_model: bool, call_fn):
        """Retry + backoff + model-fallback (coder → chat) za en LLM klic.

        P1 — zanesljivost: isti cikel kot prejšnji generate_completion, a na
        klicni funkciji `call_fn(model)` — delita ga tekstovni in agentic klic.
        """
        attempt_models = [settings.deepseek_model_coder] if use_coder_model else [settings.deepseek_model_chat]
        if use_coder_model and settings.deepseek_model_chat:
            attempt_models.append(settings.deepseek_model_chat)  # fallback na chat

        last_error: Optional[Exception] = None
        for model in attempt_models:
            for attempt in range(self.max_retries):
                try:
                    return await call_fn(model)
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    # Modelov error (400/404/422) → zamenjaj model, ne ponavljaj istega.
                    if status in (400, 404, 422):
                        last_error = e
                        break  # naslednji model
                    # Prehodna (429/5xx) → retry z backoff.
                    if status in (429,) or status >= 500:
                        import asyncio
                        await asyncio.sleep(self.backoff * (2 ** attempt))
                        last_error = e
                        continue
                    last_error = e
                    break
                except Exception as e:  # network/timeout → retry
                    import asyncio
                    await asyncio.sleep(self.backoff * (2 ** attempt))
                    last_error = e
                    continue
        raise RuntimeError(f"LLM klic ni uspel po vseh poskusih: {last_error}")

    async def generate_completion(
        self,
        prompt: str,
        system_prompt: str = "Ti si avtonomni AI inženir v sistemu Rob AI Studio.",
        use_coder_model: bool = True,
    ) -> str:
        """Pošlje zahtevek na DeepSeek API z retry, model-fallback in guardom.

        P1 — zanesljivost:
        - Retry + backoff (3 poskusi) za prehodne napake (429, 5xx).
        - Model-fallback: če `coder` pade na modelovem errorju (400/404/422),
          poskusi `chat`. To je varno za LoopX, ki nima lastnega model-retry-ja.
        - Guard: `max_completion_tokens` iz settings (če nastavljen) omeji izhod.
        """
        if not settings.is_real_key_available():
            # Determinističen odziv za lokalno testiranje brez veljavnega API ključa
            return f"# Simulated DeepSeek Output for prompt: {prompt[:30]}...\n# Mode: Autopilot Green"
        return await self._retry_models(
            use_coder_model, lambda m: self._complete_with(prompt, system_prompt, m)
        )

    async def complete_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "auto",
        use_coder_model: bool = True,
    ) -> Dict[str, Any]:
        """Agentic klic z orodji (function-calling). Vrne message dict:
        `{"content": ..., "tool_calls": [...]}` (lahko tudi `reasoning_content`).
        Enak retry/backoff/model-fallback kot generate_completion.
        """
        if not settings.is_real_key_available():
            return {"content": "# Simulated DeepSeek Output (tool-use)\n# Mode: Autopilot Green",
                    "tool_calls": None}
        return await self._retry_models(
            use_coder_model, lambda m: self._complete_with_tools_once(messages, tools, tool_choice, m)
        )
