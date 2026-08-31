"""Unit testi za core/reality_check.py (pogodbeni pregled proti realnim podatkom).

Ujame module, ki so 'zeleni na svojih testih', ampak napačni proti realnemu
sistemu (npr. health_metrics z logiko state=='running')."""

import json
import time

import pytest

from core import reality_check


def _write_module(root, project, code, export="collect_metrics"):
    d = root / "actions" / project
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{project}.py").write_text(code, encoding="utf-8")
    (d / "__init__.py").write_text(f"from .{project} import {export}\n", encoding="utf-8")


def _write_real_state(root, state="idle"):
    rob_ai = root / ".rob_ai"
    rob_ai.mkdir(parents=True, exist_ok=True)
    (rob_ai / "daemon.json").write_text(
        json.dumps({"state": state, "heartbeat_ts": int(time.time())}), encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(reality_check, "PROJECT_ROOT", tmp_path)
    return tmp_path


def test_correct_module_passes(env):
    """Pravilna healthy logika (idle + svež heartbeat → healthy True) → ok."""
    _write_real_state(env, "idle")
    _write_module(env, "good", '''
import json, time
from pathlib import Path
def collect_metrics(base_dir="."):
    d = json.loads((Path(base_dir) / ".rob_ai" / "daemon.json").read_text())
    st = d.get("state")
    fresh = time.time() - float(d.get("heartbeat_ts", 0)) < 300
    normal = st in {"idle","running","running_task","running_tick","boot","ensure_services"}
    return {"daemon": {"state": st}, "healthy": normal and fresh}
''')
    assert reality_check.run_reality_check("good", env)["ok"] is True


def test_buggy_healthy_logic_fails(env):
    """health_metrics bug: healthy = state=='running' → fail (real daemon je idle)."""
    _write_real_state(env, "idle")
    _write_module(env, "buggy", '''
import json
from pathlib import Path
def collect_metrics(base_dir="."):
    d = json.loads((Path(base_dir) / ".rob_ai" / "daemon.json").read_text())
    return {"daemon": {"state": d.get("state")}, "healthy": d.get("state") == "running"}
''')
    res = reality_check.run_reality_check("buggy", env)
    assert res["ok"] is False
    assert any("healthy" in i for i in res["issues"])


def test_wrong_reported_state_fails(env):
    """Modul poroča state='running', realni daemon je 'idle' → fail."""
    _write_real_state(env, "idle")
    _write_module(env, "wrong", '''
def collect_metrics(base_dir="."):
    return {"daemon": {"state": "running"}, "healthy": True}
''')
    res = reality_check.run_reality_check("wrong", env)
    assert res["ok"] is False
    assert any("state" in i for i in res["issues"])


def test_crash_on_real_data_fails(env):
    """Modul pade ob realnih podatkih → fail."""
    _write_real_state(env, "idle")
    _write_module(env, "boom", '''
def collect_metrics(base_dir="."):
    raise RuntimeError("boom")
''')
    res = reality_check.run_reality_check("boom", env)
    assert res["ok"] is False
    assert any("real-run fail" in i for i in res["issues"])


def test_missing_module_fails(env):
    assert reality_check.run_reality_check("ne_obstaja", env)["ok"] is False


def test_invalid_project_name_rejected(env):
    """Neveljaven project name (import injekcija) → zavrnjen pred importom."""
    assert reality_check.run_reality_check("..\\evil", env)["ok"] is False
    assert reality_check.run_reality_check("a.b", env)["ok"] is False


def test_data_dir_param_recognized(env):
    """Modul s parametrom `data_dir` se pokliče z realnim korenom → crash ujet."""
    _write_real_state(env, "idle")
    _write_module(env, "dirmod", '''
def collect_status(data_dir="."):
    raise RuntimeError("napačna pot (data_dir)")
''', export="collect_status")
    res = reality_check.run_reality_check("dirmod", env)
    assert res["ok"] is False
    assert any("real-run fail" in i for i in res["issues"])
