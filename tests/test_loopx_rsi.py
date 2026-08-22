"""Unit testi za RSI zanko (načrt 3.1–3.5) v LoopX.

Osredotočeni so na jedro logike zanke in NE kličejo pravega LLM-a.
Za izolacijo uporabljajo tmp cwd (monkeypatch.chdir), da se ne dotaknejo
dejanske mape actions/ niti produkcijške memory.db.
"""
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from core.loopx_bridge import LoopXEngineBridge


# --------------------------------------------------------------------------- #
#  Pomožne funkcije — brez zunanjih virov
# --------------------------------------------------------------------------- #

def test_parse_patched_files_izloci_bloke(tmp_path, monkeypatch):
    """3.2 — parser pretvori '### FILE:' bloke v dict datotek.

    Obnašanje od Tier-1: parser iz vsake poti izvleče le **goli basename**
    (poslednji segment po '/'), ker `_apply_patch` (3.4) sprejme zgolj
    basename — pot s separatorjem bi bila varnostno zavrnjena. Test zato
    pričakuje basename ključe, ne polnih poti.
    """
    monkeypatch.chdir(tmp_path)
    llm_odgovor = (
        "Odpravil napako.\n"
        "### FILE: actions/demo/main.py\n```python\nprint(1)\n```\n"
        "### FILE: actions/demo/schemas.py\n```python\nclass X: pass\n```\n"
    )
    files = LoopXEngineBridge._parse_patched_files(llm_odgovor)
    assert set(files.keys()) == {
        "main.py",
        "schemas.py",
    }
    assert files["main.py"] == "print(1)"
    assert files["schemas.py"] == "class X: pass"


def test_classify_error_povzame_tip(tmp_path, monkeypatch):
    """3.3 — povzame ExceptionName iz tracebacka."""
    monkeypatch.chdir(tmp_path)
    assert (
        LoopXEngineBridge._classify_error("Traceback\nImportError: no module")
        == "ImportError"
    )
    assert (
        LoopXEngineBridge._classify_error("Failed\nValueError: bad value")
        == "ValueError"
    )
    assert LoopXEngineBridge._classify_error("nobenega vzorca") == "UNKNOWN"


# --------------------------------------------------------------------------- #
#  3.4 — Varnostni filter apply_patch
# --------------------------------------------------------------------------- #

def _navidezni_engine(tmp_path, monkeypatch) -> LoopXEngineBridge:
    """Inštanica LoopX v izoliranem tmp cwd."""
    monkeypatch.chdir(tmp_path)
    engine = LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")
    # Usmerimo target_dir v izolirano pot (ne pravo actions/)
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    return engine


def test_apply_patch_samo_basename_v_modulu(tmp_path, monkeypatch):
    """3.4 — dovoljeni so le goli .py v target_dir; traversal/abs zavrnjen."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    patched = {
        "main.py": "x = 1",
        "schemas.py": "y = 2",
        "../../../etc/passwd": "EVIL",        # traversal navzgor
        "/tmp/outside.py": "EVIL2",           # absolutna pot
        "dir/file.py": "EVIL3",               # podmreža
        "readme.txt": "note",                 # ni .py
    }
    written = engine._apply_patch(patched)

    assert written == 2
    modul = tmp_path / "actions" / "demo_service"
    assert (modul / "main.py").exists()
    assert (modul / "schemas.py").exists()
    # Nobenih tujih artefaktov
    assert sorted(p.name for p in modul.iterdir()) == ["main.py", "schemas.py"]


def test_apply_patch_test_lock_tamper_zavrne_obstojeci_test(tmp_path, monkeypatch):
    """P1 — LLM ne sme SPREMENITI ŽE OBSTOJEČE test datoteke (test tamper)."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    modul = tmp_path / "actions" / "demo_service"
    (modul / "test_foo.py").write_text("def test_orig():\n    assert True\n", encoding="utf-8")
    original = (modul / "test_foo.py").read_text(encoding="utf-8")

    # LLM poskusi POPRAVITI assert (sprejet X) → mora biti zavrnjen.
    patched = {"test_foo.py": "def test_orig():\n    assert False\n"}
    written = engine._apply_patch(patched)
    assert written == 0
    # Test razširitve ostaja nespremenjen.
    assert (modul / "test_foo.py").read_text(encoding="utf-8") == original


def test_apply_patch_test_lock_dovoli_kreiranje_novega_testa(tmp_path, monkeypatch):
    """P1 — ob PRVOTNI gradnji LLM lahko USTVARI nov test (ni tamper)."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    modul = tmp_path / "actions" / "demo_service"
    # test_foo.py še NE obstaja → nova ustvaritev legitimno dovoljena.
    patched = {"test_bar.py": "def test_bar():\n    assert 1 + 1 == 2\n"}
    written = engine._apply_patch(patched)
    assert written == 1
    assert (modul / "test_bar.py").exists()


def test_read_module_sources_prebere_py(tmp_path, monkeypatch):
    """Bere .py datoteke modula za posredovanje LLM-ju."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    modul = tmp_path / "actions" / "demo_service"
    (modul / "main.py").write_text("def f():\n    pass\n", encoding="utf-8")

    sources = engine._read_module_sources()
    assert "main.py" in sources
    assert "def f():" in sources["main.py"]


# --------------------------------------------------------------------------- #
#  Kontrolni tok zanke
# --------------------------------------------------------------------------- #

def test_execute_and_heal_vrne_true_ob_zelenem_testu(tmp_path, monkeypatch):
    """3.5 — zelen cikel vrne True in zabeleži GREEN."""
    engine = _navidezni_engine(tmp_path, monkeypatch)

    # Docker šunemo na »ni na voljo«, da verifikacija teče v HOST fallback
    # (determinističen unit test zanke; prvi mock subprocess.run gre torej
    # direktno na pytest, ne na `docker info`).
    # P3 pre-gate izključimo (mock zelen): preverjamo pytest zanko, ne Ruff-a.
    with mock.patch.object(engine, "_verify_ruff", return_value=(True, "")), \
         mock.patch.object(engine, "_docker_available", return_value=False), \
         mock.patch.object(
             subprocess, "run",
             return_value=mock.Mock(returncode=0, stderr="", stdout="ok"),
         ):
        result = engine.execute_and_heal("build demo")

    assert result is True
    # Stanje je šlo v VERIFIED_GREEN
    reg = Path(tmp_path / ".loopx" / "registry.json")
    assert reg.exists()


def test_execute_and_heal_brez_healinga_vrne_false(tmp_path, monkeypatch):
    """3.1–3.3 — rdeč test + nič popravka → zgodnja prekinitev ob ponavljajoči napaki.

    Nova značilnost: ko se ista error_type (npr. ValueError) ponovi ≥
    REPEAT_ABORT_AFTER-krat, se tek zgodaj prekine (ne kuri LLM do max_attempts).
    """
    engine = _navidezni_engine(tmp_path, monkeypatch)

    # pytest zmeraj rdeč (returncode 1, ista ValueError); _heal_once ne najde popravka.
    with mock.patch.object(engine, "_verify_ruff", return_value=(True, "")), \
         mock.patch.object(
        subprocess, "run", return_value=mock.Mock(returncode=1, stderr="X\nValueError: n", stdout="")
    ), mock.patch.object(engine, "_heal_once", return_value=(False, "ni sprememb")):
        result = engine.execute_and_heal("build demo")

    assert result is False
    # Zgodnja prekinitev ob ponavljajoči napaki → current_attempt = prag, ne max.
    reg = Path(tmp_path / ".loopx" / "registry.json")
    import json
    with reg.open(encoding="utf-8") as f:
        state = json.load(f)
    assert state["status"] == "FAILED"
    assert state["current_attempt"] == engine.REPEAT_ABORT_AFTER


def test_execute_and_heal_uspeh_po_healingu(tmp_path, monkeypatch):
    """3.1 — po enem uspešnem popravku naslednji cikel postane zelen."""
    engine = _navidezni_engine(tmp_path, monkeypatch)

    # returncodes: [1 (rdeč), 0 (zelen)]. _heal_once uspešno popravi (vrača True).
    # `_docker_available` silimo na False, da gre verifikacija v HOST fallback:
    # sicer bi prvi vnos iteratorja (returncode=1) porabil `docker info` namesto
    # pytest-a in zanka bi ostala na attempt=1. S False prv1 in drugi vnos gresta
    # izključno na pytest klica (rdeč → heal → zelen), kar potrdi attempt=2.
    run_results = iter([
        mock.Mock(returncode=1, stderr="ImportError: no module named x", stdout=""),
        mock.Mock(returncode=0, stderr="", stdout="ok"),
    ])

    # P3 pre-gate izključimo (Ruff zelen), da ne porabi mock-anih vnosov.
    with mock.patch.object(engine, "_verify_ruff", return_value=(True, "")), \
         mock.patch.object(engine, "_docker_available", return_value=False), \
         mock.patch.object(subprocess, "run", side_effect=lambda *a, **k: next(run_results)), \
         mock.patch.object(engine, "_heal_once", return_value=(True, "popravil main.py")):
        result = engine.execute_and_heal("build demo")

    assert result is True
    reg = Path(tmp_path / ".loopx" / "registry.json")
    import json
    with reg.open(encoding="utf-8") as f:
        state = json.load(f)
    # Po prvem neuspehu je healing deloval in nato GREEN
    assert state["status"] == "VERIFIED_GREEN"
    assert state["current_attempt"] == 2


# --------------------------------------------------------------------------- #
#  P3 — Ruff pre-gate (F821)
# --------------------------------------------------------------------------- #

def test_verify_ruff_ne_blokira_ker_manjka(tmp_path, monkeypatch):
    """Ruff ni na PATH → pre-gate vrne (True,"") — veriga se NADALJUJE."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    monkeypatch.setattr("core.loopx_bridge.shutil.which", lambda _: None)
    ok, msg = engine._verify_ruff()
    assert ok is True
    assert msg == ""


def test_verify_ruff_zelen(tmp_path, monkeypatch):
    """Ruff čist (returncode 0) → (True,"")."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    monkeypatch.setattr("core.loopx_bridge.shutil.which", lambda _: "/x/ruff")
    with mock.patch.object(subprocess, "run",
                           return_value=mock.Mock(returncode=0, stdout="", stderr="")):
        ok, msg = engine._verify_ruff()
    assert ok is True


def test_verify_ruff_ujame_f821(tmp_path, monkeypatch):
    """Ruff najde F821 (undefined name) → (False, portinfo z razlogom)."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    monkeypatch.setattr("core.loopx_bridge.shutil.which", lambda _: "/x/ruff")
    with mock.patch.object(subprocess, "run", return_value=mock.Mock(
            returncode=1, stdout="F821 undefined name 'foo'", stderr="")):
        ok, msg = engine._verify_ruff()
    assert ok is False
    assert "F821" in msg


def test_verify_ruff_ob_izjemi_ne_blokira(tmp_path, monkeypatch):
    """Če Ruff klic sproži izjemo (timeout/napaka) → ne blokira, vzame pytest."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    monkeypatch.setattr("core.loopx_bridge.shutil.which", lambda _: "/x/ruff")
    with mock.patch.object(subprocess, "run", side_effect=TimeoutExpiredStub()):
        ok, _msg = engine._verify_ruff()
    assert ok is True


class TimeoutExpiredStub(Exception):
    pass


# --------------------------------------------------------------------------- #
#  Korak 1 — agentic tool-use (_execute_tool, _heal_agentic)
# --------------------------------------------------------------------------- #

def test_execute_tool_write_spostuje_test_lock_in_traversal(tmp_path, monkeypatch):
    """write_file: traversal se neutralizira na basename znotraj modula;
    obstoječi test (vsebina > STUB_PRAH) se zavrne (Test-Locking)."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    modul = tmp_path / "actions" / "demo_service"
    # traversal → basename se zapiše ZNOTRAJ modula (ne zunaj).
    res = engine._execute_tool("write_file", {"path": "../../evil.py", "content": "x = 1"})
    assert res["ok"] is True
    assert (modul / "evil.py").exists()
    # obstoječi test → zavrnjen, vsebina nespremenjena.
    (modul / "test_foo.py").write_text("def test_orig():\n    assert True\n", encoding="utf-8")
    res2 = engine._execute_tool("write_file", {"path": "test_foo.py", "content": "def test_orig():\n    assert False\n"})
    assert res2["ok"] is False
    assert "def test_orig():\n    assert True" in (modul / "test_foo.py").read_text(encoding="utf-8")


def test_execute_tool_list_in_read(tmp_path, monkeypatch):
    """list_files/read_file delujeta; traversal read → ok False; neznano orodje → error."""
    engine = _navidezni_engine(tmp_path, monkeypatch)
    modul = tmp_path / "actions" / "demo_service"
    (modul / "main.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    lst = engine._execute_tool("list_files", {})
    assert lst["ok"] is True and "main.py" in lst["files"]
    rd = engine._execute_tool("read_file", {"path": "main.py"})
    assert rd["ok"] is True and "def f():" in rd["content"]
    bad = engine._execute_tool("read_file", {"path": "../outside.py"})
    assert bad["ok"] is False
    unk = engine._execute_tool("neznano", {})
    assert unk["ok"] is False


def _engine_direct(tmp_path, monkeypatch):
    """Inštanica v izoliranem tmp cwd z modulom demo_service."""
    monkeypatch.chdir(tmp_path)
    engine = LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    return engine


def test_heal_agentic_tool_call_nato_content_napise_datoteko(tmp_path, monkeypatch):
    """write_file tool_call → nato končni content → datoteka zapisana, True, 2 LLM klica."""
    engine = _engine_direct(tmp_path, monkeypatch)
    calls = {"n": 0}

    async def fake_tools(messages, tools, tool_choice="auto", use_coder_model=True):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": None, "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "write_file",
                             "arguments": json.dumps({"path": "main.py", "content": "def f():\n    return 1\n"})}}]}
        return {"content": "Končano.", "tool_calls": None}

    with mock.patch.object(engine.llm, "complete_with_tools", side_effect=fake_tools):
        ok, _report = engine._heal_agentic("prompt", "system")
    assert ok is True
    assert (tmp_path / "actions" / "demo_service" / "main.py").exists()
    assert calls["n"] == 2
    assert engine.llm_calls == 2


def test_heal_agentic_pade_na_text_ob_izjemi(tmp_path, monkeypatch):
    """Ob izjemi complete_with_tools → padec na _heal_text; llm_calls == 2 (brez dvojnega štetja)."""
    engine = _engine_direct(tmp_path, monkeypatch)

    async def boom(*a, **k):
        raise RuntimeError("tools ne podpira")

    async def fake_text(prompt, system_prompt, use_coder_model=True):
        return "### FILE: main.py\n```python\ndef f():\n    return 1\n```\n"

    with mock.patch.object(engine.llm, "complete_with_tools", side_effect=boom), \
         mock.patch.object(engine.llm, "generate_completion", side_effect=fake_text):
        ok, _ = engine._heal_agentic("prompt", "system")
    assert ok is True
    assert (tmp_path / "actions" / "demo_service" / "main.py").exists()
    assert engine.llm_calls == 2  # 1 tool + 1 text — brez dvojnega štetja


def test_heal_agentic_uspeh_brez_file_blokov_prek_write_file(tmp_path, monkeypatch):
    """Samo write_file (končni odgovor brez ### FILE:) → True."""
    engine = _engine_direct(tmp_path, monkeypatch)
    calls = {"n": 0}

    async def fake_tools(messages, tools, tool_choice="auto", use_coder_model=True):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": None, "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "write_file", "arguments": json.dumps({"path": "main.py", "content": "x = 1"})}}]}
        return {"content": "Končano.", "tool_calls": None}

    with mock.patch.object(engine.llm, "complete_with_tools", side_effect=fake_tools):
        ok, _ = engine._heal_agentic("prompt", "system")
    assert ok is True


def test_heal_agentic_trim_pri_majhnem_budgetu(tmp_path, monkeypatch):
    """Korak 3 — tudi ob agresivnem trim budgetu se agentic zanka ne zlomi
    (tool_call_id ostanejo parni; varni padec ne trima sredi cikla)."""
    engine = _engine_direct(tmp_path, monkeypatch)
    (tmp_path / "actions" / "demo_service" / "big.py").write_text("x = 1\n" * 5000, encoding="utf-8")
    calls = {"n": 0}

    async def fake_tools(messages, tools, tool_choice="auto", use_coder_model=True):
        # Parnost invariant: vsak tool ima svojega assistant predhodnika.
        tool_ids = [m.get("tool_call_id") for m in messages if m.get("role") == "tool"]
        asst_ids = [tc["id"] for m in messages if m.get("role") == "assistant" for tc in (m.get("tool_calls") or [])]
        assert all(i in asst_ids for i in tool_ids), "tool brez predhodnika"
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": None, "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "write_file",
                             "arguments": json.dumps({"path": "main.py", "content": "def f():\n    return 1\n"})}}]}
        if calls["n"] == 2:
            return {"content": None, "tool_calls": [{
                "id": "c2", "type": "function",
                "function": {"name": "read_file", "arguments": json.dumps({"path": "big.py"})}}]}
        return {"content": "Končano.", "tool_calls": None}

    monkeypatch.setattr(LoopXEngineBridge, "_agentic_context_budget", lambda self: 500)
    with mock.patch.object(engine.llm, "complete_with_tools", side_effect=fake_tools):
        ok, _ = engine._heal_agentic("prompt", "system")
    assert ok is True
