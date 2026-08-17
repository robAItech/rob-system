"""Testi za P0 (spec_hint v LLM prompt) in P2 (gbrain absolutni db + target-lock).

Brez pravih LLM/Docker — vse mocka. Preveri:
- P2/gbrain: default db_path se razreši absolutno iz repo korena; eksplicitni tmp ostane.
- P2/target-lock: drugi build istega targeta ne dobi locka; release potem ok.
- P0: _heal_once vstavi spec_hint v prompt; prazna → brez bloka.
"""
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.gbrain_bridge import GBrainBridge, PROJECT_ROOT
from core.loopx_bridge import LoopXEngineBridge


# ------------------------------------------------------------------ #
#  P2 — gbrain absolutni db_path
# ------------------------------------------------------------------ #
def test_gbrain_privzeti_db_path_absoluten():
    """Default (relativni) db_path se razreši na repo koren, ne cwd."""
    g = GBrainBridge()
    assert g.db_path.is_absolute()
    assert g.db_path.resolve() == (PROJECT_ROOT / ".rob_ai" / "memory.db").resolve()


def test_gbrain_eksplicitni_tmp_db_path_ostane(tmp_path):
    """Eksplicitni (absolutni) db_path — kot v tmp-testeh — ostane nespremenjen."""
    db = tmp_path / "x" / "memory.db"
    g = GBrainBridge(db_path=db)
    assert g.db_path == db  # ni preslika v repo koren


# ------------------------------------------------------------------ #
#  P2 — target-lock (atomic O_EXCL)
# ------------------------------------------------------------------ #
def test_target_lock_blokira_drugi_build(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    e1 = LoopXEngineBridge("demo_service")
    e2 = LoopXEngineBridge("demo_service")
    assert e1._acquire_target_lock(timeout=0.2) is True
    assert e2._acquire_target_lock(timeout=0.2) is False  # already held
    e1._release_target_lock()
    assert e2._acquire_target_lock(timeout=0.2) is True  # po release → ok
    e2._release_target_lock()


def test_execute_and_heal_sprosti_lock_v_finally(tmp_path, monkeypatch):
    """Tudi ob failu se lock na koncu sprosti."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    e = LoopXEngineBridge("demo_service")
    with mock.patch.object(e, "_acquire_target_lock", return_value=True):
        # _heal_loop mock-an → False; lock mora biti release.
        with mock.patch.object(e, "_heal_loop", return_value=False):
            r = e.execute_and_heal("build", spec_hint="")
        assert r is False
        # Lock ne obstaja več (release v finally).
        assert not e._lock_path().exists()


# ------------------------------------------------------------------ #
#  P0 — spec_hint v LLM prompt
# ------------------------------------------------------------------ #
def _engine_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "actions" / "svc").mkdir(parents=True, exist_ok=True)
    (tmp_path / "actions" / "svc" / "svc.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    e = LoopXEngineBridge("svc")
    e.target_dir = (tmp_path / "actions" / "svc").resolve()
    return e


def test_heal_once_vkljuci_spec_hint(tmp_path, monkeypatch):
    """spec_hint nastavljen → prompt vsebuje 'SPEC (arhitekturna usmeritev)'."""
    monkeypatch.chdir(tmp_path)
    e = _engine_tmp(tmp_path, monkeypatch)
    captured = {}

    async def fake(prompt, system_prompt, use_coder_model=False):
        captured["prompt"] = prompt
        return "### FILE: svc.py\n```python\ndef f():\n    return 2\n```\n"

    with mock.patch.object(e.llm, "generate_completion", side_effect=fake):
        e.spec_hint = "Pydantic V2 s strogimi validatorji"
        ok, _ = e._heal_once("Traceback\nValueError: x", "d", kind="python")
    assert ok is True
    assert "arhitekturna usmeritev izvedbe" in captured["prompt"]
    assert "Pydantic V2" in captured["prompt"]


def test_heal_once_prazna_spec_hint_ni_v_promptu(tmp_path, monkeypatch):
    """spec_hint prazen → prompt NIMA bloka 'SPEC'."""
    monkeypatch.chdir(tmp_path)
    e = _engine_tmp(tmp_path, monkeypatch)
    captured = {}

    async def fake(prompt, system_prompt, use_coder_model=False):
        captured["prompt"] = prompt
        return "### FILE: svc.py\n```python\ndef f():\n    return 2\n```\n"

    with mock.patch.object(e.llm, "generate_completion", side_effect=fake):
        e.spec_hint = ""  # ni nastavIt postaja
        ok, _ = e._heal_once("Traceback\nValueError: x", "d", kind="python")
    assert ok is True
    assert "arhitekturna usmeritev izvedbe" not in captured["prompt"]
