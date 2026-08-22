"""Testi za povezavo graphify v LLM kontekst (render_context → RSI prompt).

Ni pravih LLM/Docker klicev — vse se mocka. Preveri, da:
1. render_context vrne compact kode-graf niz (ne preseže max_chars).
2. render_context tolerira manjkajoč graf (gradi na zahtevo).
3. LoopX _heal_once vstavi graf-kontekst v LLM prompt.
4. _heal_once preživi izjemo render_context (nadaljuje brez grafa).
"""
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings
from core.graphify_bridge import GraphifyBridge
from core.loopx_bridge import LoopXEngineBridge


# ------------------------------------------------------------------ #
#  Fixture: engine v izoliranem tmp cwd + graf file
# ------------------------------------------------------------------ #
@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_build_code_graph_atomicno_zapise_veljaven_json(isolated):
    """Korak 7 — atomični zapis: veljaven JSON, brez tmp ostankov."""
    gb = GraphifyBridge()
    gb.build_code_graph()
    data = json.loads((isolated / ".rob_ai" / "graph.json").read_text(encoding="utf-8"))
    assert "nodes" in data and "edges" in data
    assert list((isolated / ".rob_ai").glob("graph.json.*.tmp")) == []


def _write_graph(path: Path, nodes=None) -> None:
    """Zapiši minimalni .rob_ai/graph.json v `path`."""
    nodes = nodes or {
        "core/orchestrator.py": {"classes": ["RobAIOrchestrator"], "functions": [], "imports": ["core.loopx_bridge"]},
        "actions/demo_service/main.py": {"classes": [], "functions": ["handle"], "imports": ["demo_service.demo_service"]},
        "actions/demo_service/demo_service.py": {"classes": ["Demo"], "functions": ["run"], "imports": ["os", "json"]},
        "src/server.ts": {"classes": [], "functions": [], "imports": []},
    }
    g = {"nodes": nodes, "edges": []}
    (path / ".rob_ai").mkdir(parents=True, exist_ok=True)
    (path / ".rob_ai" / "graph.json").write_text(json.dumps(g), encoding="utf-8")


# ------------------------------------------------------------------ #
#  render_context
# ------------------------------------------------------------------ #
def test_render_context_vrne_compact_graf(isolated):
    _write_graph(isolated)
    gb = GraphifyBridge()
    ctx = gb.render_context("demo_service", max_chars=2000)
    assert "CODE GRAPH" in ctx
    assert "[core]" in ctx
    assert "[actions]" in ctx
    # Vplivi za demo_service se sklicujejo na njegove datoteke.
    assert "demo_service" in ctx


def test_render_context_omeji_dolzino(isolated):
    _write_graph(isolated)
    gb = GraphifyBridge()
    ctx = gb.render_context("demo_service", max_chars=120)
    # Cap (120) + oznaka izrezljavosti; realna rezultat < 200.
    assert len(ctx) <= 400
    assert "znakov izpu" in ctx  # presežen cap → oznaka


def test_render_context_ob_manjkajocem_grafu_zgradi(isolated, monkeypatch):
    """Graf ne obstaja → build_code_graph se prikliče, vrne niz (ne crash)."""
    gb = GraphifyBridge()
    with mock.patch.object(GraphifyBridge, "build_code_graph") as mock_build:
        ctx = gb.render_context("demo_service")
    mock_build.assert_called_once()
    assert isinstance(ctx, str)


# ------------------------------------------------------------------ #
#  LoopX _heal_once → graf-kontekst v prompt
# ------------------------------------------------------------------ #
def _engine_with_graph(tmp_path):
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    (tmp_path / "actions" / "demo_service" / "demo_service.py").write_text(
        "def run():\n    return 1\n", encoding="utf-8"
    )
    eng = LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")
    eng.target_dir = (tmp_path / "actions" / "demo_service").resolve()
    return eng


def test_heal_once_vkljuci_graf_kontekst(tmp_path, monkeypatch):
    """_heal_once prompt vsebuje graf-kontekst (mock render_context → "GRAF")."""
    monkeypatch.chdir(tmp_path)
    _write_graph(tmp_path)
    eng = _engine_with_graph(tmp_path)

    captured = {}

    async def fake_generate_completion(prompt, system_prompt, use_coder_model=False):
        captured["prompt"] = prompt
        return "### FILE: demo_service.py\n```python\ndef run():\n    return 2\n```\n"

    monkeypatch.setattr(settings, "llm_tool_use", False)  # tekstovna pot (mock generate_completion)
    with mock.patch.object(eng, "graphify") as mock_graph, \
         mock.patch.object(eng.llm, "generate_completion", side_effect=fake_generate_completion):
        mock_graph.render_context.return_value = "GRAF_SPECIAL_MARKER"
        ok, _report = eng._heal_once("Traceback\nValueError: x", "directive", kind="python")

    assert ok is True
    assert "KODNI GRAF" in captured["prompt"]
    assert "GRAF_SPECIAL_MARKER" in captured.get("prompt", "")


def test_heal_once_prezivi_izjemo_render_context(tmp_path, monkeypatch):
    """Če render_context pade, _heal_once nadaljuje brez grafa (ne crash)."""
    monkeypatch.chdir(tmp_path)
    _write_graph(tmp_path)
    eng = _engine_with_graph(tmp_path)

    captured = {}

    async def fake_generate_completion(prompt, system_prompt, use_coder_model=False):
        captured["prompt"] = prompt
        return "### FILE: demo_service.py\n```python\ndef run():\n    return 2\n```\n"

    monkeypatch.setattr(settings, "llm_tool_use", False)  # tekstovna pot (mock generate_completion)
    with mock.patch.object(eng, "graphify") as mock_graph, \
         mock.patch.object(eng.llm, "generate_completion", side_effect=fake_generate_completion):
        mock_graph.render_context.side_effect = RuntimeError("graf padel")
        ok, _report = eng._heal_once("Traceback\nValueError: x", "directive", kind="python")

    assert ok is True  # healing še vedno uspe brez grafa
    assert "KODNI GRAF" not in captured["prompt"]  # graf izpuščen


def test_heal_once_popravi_to_dobi_obstojece_sources(tmp_path, monkeypatch):
    """"Popravi to": obstoječi modul (z vsebino) → LLM prompt vsebuje obstoječo
    kodo (sources), ne samo praznih stubs — da lahko LLM ustrezno popravi."""
    monkeypatch.chdir(tmp_path)
    _write_graph(tmp_path)
    eng = _engine_with_graph(tmp_path)   # ustvari demo_service.py z `def run(): return 1`
    captured = {}

    async def fake_generate_completion(prompt, system_prompt, use_coder_model=False):
        captured["prompt"] = prompt
        return "### FILE: demo_service.py\n```python\ndef run():\n    return 2\n```\n"

    monkeypatch.setattr(settings, "llm_tool_use", False)  # tekstovna pot (mock generate_completion)
    with mock.patch.object(eng, "graphify") as mock_graph, \
         mock.patch.object(eng.llm, "generate_completion", side_effect=fake_generate_completion):
        mock_graph.render_context.return_value = ""
        ok, _report = eng._heal_once("Traceback\nValueError: x", "popravi logiko", kind="python")

    assert ok is True
    # LLM vidi obstoječo vsebino modula (sources), ne praznih stubs.
    assert "def run():" in captured["prompt"]
    assert "return 1" in captured["prompt"]   # obstoječa implementacija, ne stub
