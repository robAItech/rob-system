"""Testi za P0 (spec_hint v LLM prompt) in P2 (gbrain absolutni db + target-lock).

Brez pravih LLM/Docker — vse mocka. Preveri:
- P2/gbrain: default db_path se razreši absolutno iz repo korena; eksplicitni tmp ostane.
- P2/target-lock: drugi build istega targeta ne dobi locka; release potem ok.
- P0: _heal_once vstavi spec_hint v prompt; prazna → brez bloka.
"""
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings
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
    e1 = LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")
    e2 = LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")
    assert e1._acquire_target_lock(timeout=0.2) is True
    assert e2._acquire_target_lock(timeout=0.2) is False  # already held
    e1._release_target_lock()
    assert e2._acquire_target_lock(timeout=0.2) is True  # po release → ok
    e2._release_target_lock()


def test_execute_and_heal_sprosti_lock_v_finally(tmp_path, monkeypatch):
    """Tudi ob failu se lock na koncu sprosti."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "actions" / "demo_service").mkdir(parents=True, exist_ok=True)
    e = LoopXEngineBridge("demo_service", db_path=tmp_path / "memory.db")
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
    e = LoopXEngineBridge("svc", db_path=tmp_path / "memory.db")
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

    monkeypatch.setattr(settings, "llm_tool_use", False)  # tekstovna pot (mock generate_completion)
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

    monkeypatch.setattr(settings, "llm_tool_use", False)  # tekstovna pot (mock generate_completion)
    with mock.patch.object(e.llm, "generate_completion", side_effect=fake):
        e.spec_hint = ""  # ni nastavIt postaja
        ok, _ = e._heal_once("Traceback\nValueError: x", "d", kind="python")
    assert ok is True
    assert "arhitekturna usmeritev izvedbe" not in captured["prompt"]


def test_db_write_lock_je_rlock_in_pisci_delajo(tmp_path):
    """Korak 7 — DB_WRITE_LOCK je RLock; 8 vzporednih pisalcev ne izgubi zapisov."""
    import threading
    from core.gbrain_bridge import DB_WRITE_LOCK, GBrainBridge
    assert type(DB_WRITE_LOCK).__name__ == "RLock"   # threading.RLock je fabrika, ne tip
    gb = GBrainBridge(tmp_path / "memory.db")
    errors = []

    def writer(i):
        try:
            gb.record_task("p", f"t{i}", "VERIFIED GREEN", verified_code="Pass")
        except Exception as e:   # pragma: no cover — če lock ne deluje
            errors.append(e)

    ts = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors
    with gb._get_connection() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM task_history").fetchone()["n"]
    assert n == 8


# ------------------------------------------------------------------ #
#  Zgodnja prekinitev na ponavljajoči napaki (učenje, ne slepo kurjenje)
# ------------------------------------------------------------------ #
def test_heal_loop_pretrga_ponavljanje_po_pragu(tmp_path, monkeypatch):
    """3× ista error_type → _heal_once klican ≤ prag-1, nato zgodaj FAILED."""
    monkeypatch.chdir(tmp_path)
    e = _engine_tmp(tmp_path, monkeypatch)
    calls = {"n": 0}

    def fake_heal_once(reason, directive, kind):
        calls["n"] += 1
        return (False, "ni popravka")

    from unittest import mock as _m
    with _m.patch.object(e, "_verify_ruff", return_value=(True, "")), \
         _m.patch.object(e, "_docker_available", return_value=False), \
         _m.patch.object(subprocess, "run",
                         return_value=_m.Mock(returncode=1, stderr="X\nValueError: n", stdout="")), \
         _m.patch.object(e, "_heal_once", side_effect=fake_heal_once):
        r = e.execute_and_heal("build")
    assert r is False
    # _heal_once klican le do praga-prvi (vsak attempt), ne do max_attempts.
    assert calls["n"] == e.REPEAT_ABORT_AFTER - 1


def test_heal_loop_razlicne_napake_ne_pretrga(tmp_path, monkeypatch):
    """Različne napake zaporedoma → NE zgodnja prekinitev, gredo skozi."""
    monkeypatch.chdir(tmp_path)
    e = _engine_tmp(tmp_path, monkeypatch)
    errors = iter(["ValueError: a", "ImportError: b", "TypeError: c", "KeyError: d"])

    from unittest import mock as _m
    def fake_run(*a, **k):
        return _m.Mock(returncode=1, stderr=next(errors, "ValueError: e"), stdout="")
    with _m.patch.object(e, "_verify_ruff", return_value=(True, "")), \
         _m.patch.object(subprocess, "run", side_effect=fake_run), \
         _m.patch.object(e, "_heal_once", return_value=(False, "x")):
        # Skrajšamo max_attempts, da test hitreje konča (različne napake ne
        # sprožijo praga → teče do max_attempts).
        e.max_attempts = 4
        r = e.execute_and_heal("build")
    assert r is False
    # Nobena posamezna napaka ne sme doseči praga za zgodnjo prekinitev
    # (zanka teče do max_attempts, ker so napake RAZLIČNE).
    assert all(n < e.repeat_abort_after for n in e._heal_fail_count.values())


# ------------------------------------------------------------------ #
#  Eval meritveno sledenje (opazljivost skozi čas)
# ------------------------------------------------------------------ #
def test_eval_history_append_rase(tmp_path, monkeypatch):
    """_append_history doda vnos; _read_history vrne naraščajoči array."""
    import evaluate_autonomy as ev
    hist = tmp_path / "eval_history.json"
    monkeypatch.setattr(ev, "HISTORY_FILE", hist)
    ev._append_history({"date": "2026-01-01T00:00Z", "passed": 1, "total": 2, "rate": 0.5})
    ev._append_history({"date": "2026-01-02T00:00Z", "passed": 2, "total": 2, "rate": 1.0})
    assert len(ev._read_history()) == 2


def test_eval_history_read_prazen_ne_crash(tmp_path, monkeypatch):
    """Brez datoteke → _read_history vrne [] in --history ne crash."""
    import evaluate_autonomy as ev
    hist = tmp_path / "nepostoji.json"
    monkeypatch.setattr(ev, "HISTORY_FILE", hist)
    assert ev._read_history() == []
