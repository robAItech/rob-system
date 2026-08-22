"""Testi za semantični spomin z embeddingi (korak 2) — BREZ omrežja.

Uporabljajo determinističen `FakeEmbedder` (token-frekvenčni vektor z
`sum(ord(c))`, ne Python `hash()` — stabilen čez teke). Globalni conftest
autouse izklopi `memory_embeddings`; ti testi se lokalno opt-inejo in zamenjajo
embedder z `cons._embedder`, da nikoli ne pride do pravega Gemini klica.
"""
import json
import math
import re
import sqlite3

import pytest

from core.config import settings
from core.memory_consolidation import MemoryConsolidator


class FakeEmbedder:
    """Determinističen embedding: token-frekvenčni normaliziran vektor."""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def embed(self, text: str):
        vec = [0.0] * self.dim
        for tok in re.findall(r"[a-zčšž0-9_]+", (text or "").lower()):
            vec[sum(ord(c) for c in tok) % self.dim] += 1.0
        n = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / n for v in vec]


class _NoneEmbedder:
    """Simulira nedosegljiv embedder (fallback na leksikalno pot)."""

    def embed(self, text: str):
        return None


def _make_consolidator(tmp_path, embedder) -> MemoryConsolidator:
    """Konsolidator z lekcijama; embedder nastavljen PRED store (brez pravega API-ja)."""
    cons = MemoryConsolidator(tmp_path / "memory.db")
    cons._embedder = embedder
    cons.store(
        "demo: NameError",
        "NameError se zgodi, ko ime ni definirano — definiraj jo.",
        project="demo", kind="pitfall", confidence=0.5,
    )
    cons.store(
        "demo: ValueError",
        "ValueError pri napačnem vhodu.",
        project="demo", kind="pitfall", confidence=0.5,
    )
    return cons


def test_recall_semantic_top_hit(tmp_path, monkeypatch):
    """Semantična pot: NameError mora biti najvišji zadetek z score > 0."""
    monkeypatch.setattr(settings, "memory_embeddings", True)
    cons = _make_consolidator(tmp_path, FakeEmbedder())
    hits = cons.recall("NameError", project="demo", limit=5)
    assert hits, "semantični recall ne sme biti prazen"
    assert hits[0]["kind"] == "pitfall"
    assert "NameError" in hits[0]["theme"]
    assert hits[0]["score"] > 0


def test_recall_semantic_rejects_unrelated(tmp_path, monkeypatch):
    """Nepovezana poizvedba → prazen seznam (cos < absolutni prag 0.20)."""
    monkeypatch.setattr(settings, "memory_embeddings", True)
    cons = _make_consolidator(tmp_path, FakeEmbedder())
    hits = cons.recall("popolnoma nepovezana poizvedba xyzq", project="demo")
    assert hits == []


def test_recall_falls_back_to_lexical_when_embed_fails(tmp_path, monkeypatch):
    """Embedder vrne None → padec na leksikalno pot (NameError še vedno zmaga)."""
    monkeypatch.setattr(settings, "memory_embeddings", True)
    cons = _make_consolidator(tmp_path, _NoneEmbedder())
    hits = cons.recall("NameError", project="demo")
    assert hits and "NameError" in hits[0]["theme"]


def test_upsert_persists_embedding(tmp_path, monkeypatch):
    """store() zapiše embedding stolpec (JSON list floatov dim=64)."""
    monkeypatch.setattr(settings, "memory_embeddings", True)
    cons = _make_consolidator(tmp_path, FakeEmbedder(dim=64))
    with sqlite3.connect(cons.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT embedding FROM semantic_memories LIMIT 1").fetchone()
    vec = json.loads(row["embedding"])
    assert isinstance(vec, list) and len(vec) == 64
    assert all(isinstance(v, float) for v in vec)


def test_recall_mixed_embedded_and_null_falls_back_to_lexical(tmp_path, monkeypatch):
    """Ena vrstica z vektorjem, ena brez → leksikalni fallback (all-or-lexical)."""
    monkeypatch.setattr(settings, "memory_embeddings", True)
    cons = _make_consolidator(tmp_path, FakeEmbedder(dim=64))
    # Druga vrstica dobi NULL embedding (simulira staro bazo pred backfill-om).
    with sqlite3.connect(cons.db_path) as conn:
        conn.execute("UPDATE semantic_memories SET embedding = NULL WHERE theme LIKE '%ValueError%'")
        conn.commit()
    hits = cons.recall("NameError", project="demo")
    assert hits and "NameError" in hits[0]["theme"]
