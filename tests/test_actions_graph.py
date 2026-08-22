"""Testi za realne odvisnostne robove action modulov (korak 5).

Brez omrežja, brez LLM. Preveri, da `core/actions_graph.py` vrne REALNE
importe med moduli (ne aspirativne GRAPH_EDGES) + MIDDLEWARE verigo.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.actions_graph import (build_action_edges, build_runtime_chain_edges, all_edges)

ROOT = Path(__file__).resolve().parents[1]

ALL_NAMES = {
    "api_gateway", "audit_trail", "auth_vault", "cache_layer", "circuit_breaker",
    "contract_schema_engine", "currency_converter", "deployment_manager", "event_bus",
    "feature_flag", "mailer", "nexus_command_deck", "observability_metrics",
    "rate_limiter", "rsi_engine", "saga_orchestrator", "task_queue", "warehouse_inventory",
}


def test_contains_known_imports():
    pairs = {(e["source"], e["target"]) for e in build_action_edges(ROOT)}
    assert ("audit_trail", "event_bus") in pairs
    assert ("cache_layer", "observability_metrics") in pairs


def test_no_self_edges():
    edges = build_action_edges(ROOT)
    assert all(e["source"] != e["target"] for e in edges)


def test_targets_are_action_modules():
    edges = build_action_edges(ROOT)
    assert all(e["source"] in ALL_NAMES and e["target"] in ALL_NAMES for e in edges)


def test_deterministic():
    assert build_action_edges(ROOT) == build_action_edges(ROOT)


def test_runtime_chain_edges():
    chain = build_runtime_chain_edges()
    assert [(e["source"], e["target"]) for e in chain] == [
        ("auth_vault", "rate_limiter"),
        ("rate_limiter", "audit_trail"),
        ("audit_trail", "event_bus"),
    ]
    assert all(e["relation"] == "MIDDLEWARE" for e in chain)


def test_all_edges_imajo_relation():
    for e in all_edges(ROOT):
        assert e["relation"] in ("IMPORTS", "MIDDLEWARE")
