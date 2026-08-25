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
        # Rezerva (OpenRouter), če DeepSeek pade po vseh retry-jih.
        self.openrouter_api_key = getattr(settings, "openrouter_api_key", "") or ""
        self.openrouter_base_url = (getattr(settings, "openrouter_base_url", "") or "").rstrip("/")
        self.last_usage: Dict[str, Any] = {}   # Korak 3: usage iz zadnjega API odgovora

    def _has_key(self) -> bool:
        """Ali ima TA klient veljaven API ključ (lastni self.api_key, ne globalni
        settings — testi konstruirajo z api_key="sk-test", kar mora veljati tudi
        v CI, kjer .env (in s tem settings ključ) ni prisoten)."""
        key = (self.api_key or "").strip()
        return bool(key and key != "sk-your-deepseek-api-key-here" and key.startswith("sk-"))

    def _has_openrouter(self) -> bool:
        """Ali je nastavljena OpenRouter rezerva (ključ sk-or-...)."""
        key = (self.openrouter_api_key or "").strip()
        return bool(key and key.startswith("sk-or-"))

    def _get_headers(self, api_key: Optional[str] = None) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key or self.api_key}",
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
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> str:
        """Pošlje zahtevek na določen model (default DeepSeek, lahko OpenRouter)."""
        endpoint = f"{(base_url or self.base_url).rstrip('/')}/chat/completions"
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
        return await self._post_once(endpoint, self._get_headers(api_key), payload)

    async def _complete_with_tools_once(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str,
        model: str,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Pošlje zahtevek z orodji (function-calling), vrne message dict."""
        endpoint = f"{(base_url or self.base_url).rstrip('/')}/chat/completions"
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
        return await self._post_message(endpoint, self._get_headers(api_key), payload)

    async def _retry_one(self, model: str, base_url: str, api_key: str, call_fn) -> tuple:
        """Retry+backoff za EN (model, provider). Vrne (ok, rezultat|napaka)."""
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                return True, await call_fn(model, base_url, api_key)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (400, 404, 422):   # modelov error → zamenjaj model
                    last_error = e
                    break
                if status in (429,) or status >= 500:   # prehodna → retry
                    import asyncio
                    await asyncio.sleep(self.backoff * (2 ** attempt))
                    last_error = e
                    continue
                last_error = e
                break
            except Exception as e:              # network/timeout → retry
                import asyncio
                await asyncio.sleep(self.backoff * (2 ** attempt))
                last_error = e
                continue
        return False, last_error

    async def _retry_models(self, use_coder_model: bool, call_fn):
        """Retry + backoff + model-fallback + PROVIDER-fallback (OpenRouter).

        P1 — zanesljivost: coder → chat (isti provider), nato — če DeepSeek
        pade po vseh poskusih — OpenRouter rezerva (isti modeli). Klicna
        funkcija prejme (model, base_url, api_key), da deli tekstovno in
        agentic pot.
        """
        attempt_models = [settings.deepseek_model_coder] if use_coder_model else [settings.deepseek_model_chat]
        if use_coder_model and settings.deepseek_model_chat:
            attempt_models.append(settings.deepseek_model_chat)  # fallback na chat

        last_error: Optional[Exception] = None
        # 1) DeepSeek (glavni provider)
        for model in attempt_models:
            ok, res = await self._retry_one(model, self.base_url, self.api_key, call_fn)
            if ok:
                return res
            last_error = res
        # 2) OpenRouter (rezerva, ko DeepSeek pade)
        if self._has_openrouter():
            for model in attempt_models:
                ok, res = await self._retry_one(model, self.openrouter_base_url, self.openrouter_api_key, call_fn)
                if ok:
                    return res
                last_error = res
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
        if not self._has_key() and not self._has_openrouter():
            # Determinističen odziv za lokalno testiranje brez veljavnega API ključa
            return f"# Simulated DeepSeek Output for prompt: {prompt[:30]}...\n# Mode: Autopilot Green"
        return await self._retry_models(
            use_coder_model, lambda m, b, k: self._complete_with(prompt, system_prompt, m, b, k)
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
        if not self._has_key() and not self._has_openrouter():
            return {"content": "# Simulated DeepSeek Output (tool-use)\n# Mode: Autopilot Green",
                    "tool_calls": None}
        return await self._retry_models(
            use_coder_model, lambda m, b, k: self._complete_with_tools_once(messages, tools, tool_choice, m, b, k)
        )
