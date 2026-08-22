"""Testi za upravljanje konteksta (korak 3) — budget heal prompta + trim agentic.

Brez omrežja. Preverijo: izločitev test datotek iz sources, `_fit_sources`
(relevanca + entry-point + determinizem), budget `_build_heal_prompt`,
`_trim_agentic_messages` (aktivni cikel atomično ohranjen), `estimate_tokens`.
"""
import json

from core.config import settings
from core.llm_client import estimate_tokens
from core.loopx_bridge import LoopXEngineBridge


def _engine(tmp_path, monkeypatch, files: dict) -> LoopXEngineBridge:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (tmp_path / "actions" / "demo_service" / name).write_text(content, encoding="utf-8")
    return LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")


def test_read_module_sources_izpusti_test_datoteke(tmp_path, monkeypatch):
    """Privzeto brez test datotek; spoštuje include_tests param in settings flag."""
    engine = _engine(tmp_path, monkeypatch, {
        "main.py": "def run():\n    return 1\n",
        "test_foo.py": "def test_foo():\n    assert True\n",
        "conftest.py": "import pytest\n",
    })
    assert set(engine._read_module_sources()) == {"main.py"}
    assert set(engine._read_module_sources(include_tests=True)) == {"main.py", "test_foo.py", "conftest.py"}
    monkeypatch.setattr(settings, "llm_heal_include_tests", True)
    assert set(engine._read_module_sources()) == {"main.py", "test_foo.py", "conftest.py"}


def test_fit_sources_obdrzi_relevantne_in_entrypoint():
    """Relevantna (traceback) + entry-point ostaneta cela; velika nerelevantna se izpusti."""
    sources = {
        "gateway.py": "def route():\n    pass\n" + ("x" * 4000),   # omenjeno v traceback
        "main.py": "from gateway import route\n" + ("y" * 3000),   # entry-point
        "utils.py": "def helper():\n    pass\n" + ("z" * 5000),     # velika, nerelevantna
        "schemas.py": "class S:\n    pass\n" + ("w" * 500),         # majhna
    }
    tb = "Traceback\nNameError in gateway.route"
    fitted, omitted, truncated = LoopXEngineBridge._fit_sources(sources, 8000, tb, "zgradi modul")
    assert "gateway.py" in fitted
    assert "main.py" in fitted
    assert "schemas.py" in fitted
    assert "utils.py" not in fitted and "utils.py" in omitted
    # Determinizem.
    assert LoopXEngineBridge._fit_sources(sources, 8000, tb, "zgradi modul") == (fitted, omitted, truncated)


def test_build_heal_prompt_spostuje_budget(tmp_path, monkeypatch):
    """Velik modul + majhen budget → prompt ≤ cap, direktiva/traceback ohranjena, manifest prisoten."""
    monkeypatch.setattr(settings, "llm_heal_prompt_chars", 6000)
    monkeypatch.setattr(settings, "llm_heal_sources_chars", 3000)
    files = {f"mod{i}.py": f"def fn{i}():\n    return {i}\n" + ("# x" * 400) for i in range(6)}
    engine = _engine(tmp_path, monkeypatch, files)
    prompt = engine._build_heal_prompt("Traceback\nValueError: x", "zgradi modul", kind="python")
    assert len(prompt) <= 6000
    assert "DIREKTIVA" in prompt
    assert "ValueError" in prompt
    assert "DATOTEKE MODULA" in prompt        # izpuščene datoteke → manifest


def test_build_heal_prompt_majhen_modul_nespremenjen(tmp_path, monkeypatch):
    """Majhen modul → prompt vsebuje vse sources cele, brez manifest vrstice."""
    engine = _engine(tmp_path, monkeypatch, {"main.py": "def run():\n    return 1\n"})
    prompt = engine._build_heal_prompt("Traceback\nValueError: x", "zgradi modul", kind="python")
    assert "def run():" in prompt
    assert "DATOTEKE MODULA" not in prompt


def _msg_size(m: dict) -> int:
    return len(json.dumps(m))


def test_trim_agentic_messages_obdrzi_aktivni_cikel():
    """Trim odreže najstarejše cele cikle; aktivni cikel (zadnji assistant+tool) atomično ohranjen."""
    system = {"role": "system", "content": "sys"}
    user = {"role": "user", "content": "usr"}
    cycles = []
    for i in range(4):
        cycles.append({"role": "assistant", "content": None,
                       "tool_calls": [{"id": f"a{i}", "function": {"name": "read_file", "arguments": "{}"}}]})
        cycles.append({"role": "tool", "tool_call_id": f"a{i}", "content": "x" * 10000})
    messages = [system, user] + cycles
    trimmed = LoopXEngineBridge._trim_agentic_messages(messages, 22000)
    assert sum(_msg_size(m) for m in trimmed) <= 22000
    assert trimmed[0] == system and trimmed[1] == user
    assert trimmed[-2]["role"] == "assistant" and trimmed[-2]["tool_calls"]
    assert trimmed[-1]["role"] == "tool"
    # Parnost: vsak tool ima svojega assistant predhodnika.
    tool_ids = [m["tool_call_id"] for m in trimmed if m.get("role") == "tool"]
    asst_ids = [tc["id"] for m in trimmed if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])]
    assert all(i in asst_ids for i in tool_ids)
    # Najstarejši cikel (a0) izpuščen.
    assert not any(m.get("tool_calls") and m["tool_calls"][0]["id"] == "a0" for m in trimmed)


def test_trim_agentic_messages_velik_aktivni_cikel_padec():
    """Če head+aktivni cikel sami presegata budget → varni padec (nespremenjeno)."""
    system = {"role": "system", "content": "s" * 300}
    user = {"role": "user", "content": "u" * 300}
    assistant = {"role": "assistant", "content": None,
                 "tool_calls": [{"id": "a0", "function": {"name": "read_file", "arguments": "{}"}}]}
    tool = {"role": "tool", "tool_call_id": "a0", "content": "x" * 2000}
    messages = [system, user, assistant, tool]
    result = LoopXEngineBridge._trim_agentic_messages(messages, 500)
    assert result == messages


def test_estimate_tokens():
    assert estimate_tokens("a" * 100) == 25
    assert estimate_tokens("") == 1
