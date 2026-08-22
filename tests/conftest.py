"""Skupne pytest fixture — globalna mrežna zaščita.

Semantični spomin (korak 2) uporablja Gemini embedder, ki bi v testih klicu
pravi API (repo `.env` ima realen `GEMINI_API_KEY`). Autouse fixture izklopi
`memory_embeddings` za VSE teste → deterministični leksikalni padec, brez
omrežja. Semantični testi se lokalno opt-inejo (`memory_embeddings=True`) in
uporabijo determinističen `FakeEmbedder` iz `tests/test_semantic_memory.py`.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_network_embeddings(monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "memory_embeddings", False)
