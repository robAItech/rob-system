"""Unit testi za RSI zanko (načrt 3.1–3.5) v LoopX.

Osredotočeni so na jedro logike zanke in NE kličejo pravega LLM-a.
Za izolacijo uporabljajo tmp cwd (monkeypatch.chdir), da se ne dotaknejo
dejanske mape actions/ niti produkcijške memory.db.
"""
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
    engine = LoopXEngineBridge("demo_service")
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
    """3.1–3.3 — rdeč test + nič popravka → po max_attempts vrne False."""
    engine = _navidezni_engine(tmp_path, monkeypatch)

    # pytest zmeraj rdeč (returncode 1); _heal_once ne najde popravka
    with mock.patch.object(engine, "_verify_ruff", return_value=(True, "")), \
         mock.patch.object(
        subprocess, "run", return_value=mock.Mock(returncode=1, stderr="X\nValueError: n", stdout="")
    ), mock.patch.object(engine, "_heal_once", return_value=(False, "ni sprememb")):
        result = engine.execute_and_heal("build demo")

    assert result is False
    # Po 5 poskusih je bil zapisan vzorec v GBRAIN (3.3) in končno stanje FAILED.
    reg = Path(tmp_path / ".loopx" / "registry.json")
    import json
    with reg.open(encoding="utf-8") as f:
        state = json.load(f)
    assert state["status"] == "FAILED"
    assert state["current_attempt"] == engine.max_attempts


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
