"""core/embedder.py — semantični embeddingi za spomin (korak 2).

Gemini API `embedContent` (model `gemini-embedding-2`, 3072-dim). Uporablja se
SAMO za izračun vektorskih embeddingov spomina (iskanje podobnosti) — nikoli za
generiranje. DeepSeek v4 Flash ostaja edini glavni LLM.

Varno: `embed()` nikoli ne dvigne izjeme — ob napaki/manjkajočem ključu vrne
None, klicatelj pa pade nazaj na leksikalni priklic. TTL-cache (uspeh 300 s /
napaka 60 s) ščiti vročo pot (_heal_once → recall) pred ponovljenimi klici.
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Optional, Tuple

import httpx

from core.config import settings

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
_OK_TTL = 300.0    # uspeh: 5 min
_FAIL_TTL = 60.0   # napaka: ponovi po 60 s (ne degradiraj večno)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Kosinusna podobnost dveh vektorjev; nič-vektor/prazno → 0.0."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class MemoryEmbedder:
    """Embedder za semantični spomin (trenutno Gemini, pripravljen za Ollama).

    Class-level cache preživi instanciranje svežega `MemoryConsolidator`-ja v
    `_gather_memory_notes` (kliče se ob vsakem heal attemptu) — uspešni
    embeddingi se ne računajo večkrat, izpadi pa se ne ponavljajo v 60 s.
    """

    _cache: Dict[str, Tuple[float, Optional[Tuple[float, ...]]]] = {}
    #          text -> (expires_monotonic, value)

    def __init__(self, model: Optional[str] = None, api: Optional[str] = None,
                 timeout: Optional[float] = None):
        self.model = model or settings.memory_embed_model
        self.api = api or settings.memory_embed_api
        self.timeout = timeout or settings.memory_embed_timeout_seconds
        self.api_key = settings.gemini_api_key

    def enabled(self) -> bool:
        """Dinamično bere settings — testi lahko zastavico monkeypatchajo v živo."""
        return bool(
            settings.memory_embeddings
            and self.api_key
            and self.api == "gemini"
        )

    def embed(self, text: str) -> Optional[List[float]]:
        """En text → vektor ali None. Nikoli ne dvigne izjeme."""
        if not self.enabled():
            return None
        now = time.monotonic()
        hit = self._cache.get(text)
        if hit and hit[0] > now:
            return list(hit[1]) if hit[1] is not None else None
        try:
            vec = self._embed_gemini(text)
        except Exception:
            self._cache[text] = (now + _FAIL_TTL, None)   # ne mečemo izjeme naprej
            return None
        self._cache[text] = (now + _OK_TTL, tuple(vec))
        return vec

    def _embed_gemini(self, text: str) -> List[float]:
        url = _GEMINI_URL.format(model=self.model)
        payload = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": text}]},
        }
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return [float(v) for v in resp.json()["embedding"]["values"]]
