import time
import asyncio
from typing import Dict, Any, Callable, Awaitable
from actions.nexus_command_deck.schemas import OrchestratorRequest, OrchestratorResponse

class MultiLLMOrchestrator:
    def __init__(self):
        # Simulirani zaledni ponudniki. V realnosti tu kličeš DeepSeek/OpenAI/Anthropic API-je.
        self.providers = {
            "DeepSeek": self._mock_deepseek,
            "Gemini": self._mock_gemini,
            "Anthropic": self._mock_anthropic,
            "OpenAI": self._mock_openai
        }
        # Nastavitve failoverja
        self.primary_fail_sim = False

    async def _mock_deepseek(self, req: OrchestratorRequest) -> str:
        await asyncio.sleep(0.1)
        if self.primary_fail_sim:
            raise ConnectionError("DeepSeek API Timeout")
        return f"[DeepSeek Coder] Generiram kodo za poizvedbo: {req.content[:20]}..."

    async def _mock_gemini(self, req: OrchestratorRequest) -> str:
        await asyncio.sleep(0.15)
        if self.primary_fail_sim:
            raise ConnectionError("Gemini API Timeout")
        return f"[Gemini Flash] Analiziram {req.content_type}: {req.content[:20]}..."

    async def _mock_anthropic(self, req: OrchestratorRequest) -> str:
        await asyncio.sleep(0.2)
        return f"[Anthropic Claude] Procesiram logiko za: {req.content[:20]}..."

    async def _mock_openai(self, req: OrchestratorRequest) -> str:
        await asyncio.sleep(0.1)
        return f"[OpenAI Fallback] Zasilni odgovor za: {req.content[:20]}..."

    def _route_request(self, content_type: str) -> str:
        if content_type == "text" and "koda" in content_type.lower():
            return "DeepSeek"
        elif content_type in ["audio", "file"]:
            return "Gemini"
        else:
            return "Anthropic"

    async def process(self, req: OrchestratorRequest) -> OrchestratorResponse:
        start_time = time.perf_counter()
        
        primary_provider = self._route_request(req.content_type)
        fallback_provider = "OpenAI"
        
        is_fallback = False
        provider_used = primary_provider
        content = ""

        try:
            handler = self.providers.get(primary_provider, self._mock_openai)
            content = await handler(req)
        except Exception as e:
            # Samodejni Failover
            is_fallback = True
            provider_used = fallback_provider
            handler = self.providers.get(fallback_provider)
            content = await handler(req)

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return OrchestratorResponse(
            content=content,
            provider=provider_used,
            latency_ms=latency_ms,
            is_fallback=is_fallback
        )
