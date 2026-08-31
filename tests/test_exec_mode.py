"""Unit testi za avtomatski team swarm (core/exec_mode + agenda.set_kind +
run_swarm promocija kind → 'team')."""

import types

import pytest

from core import agenda as ag
from core import exec_mode


def _settings(**overrides):
    base = {"team_auto_enabled": True, "team_auto_kinds": "autonomous"}
    base.update(overrides)
    return types.SimpleNamespace(**base)


# ------------------------------------------------------------------ #
#  decide_exec_mode
# ------------------------------------------------------------------ #
def test_default_single_for_non_team_kind():
    s = _settings()
    assert exec_mode.decide_exec_mode({"kind": "python", "goal": "x"}, s) == "single"


def test_kind_in_auto_kinds_uses_team():
    s = _settings()
    assert exec_mode.decide_exec_mode({"kind": "autonomous", "goal": "Zgradi modul"}, s) == "team"


def test_doc_goal_keeps_single_for_auto_kind():
    # Doc-guard: dokumentne naloge NISO team (team gradi module).
    s = _settings()
    assert exec_mode.decide_exec_mode(
        {"kind": "autonomous", "goal": "Napiši markdown predlog"}, s) == "single"
    assert exec_mode.decide_exec_mode(
        {"kind": "autonomous", "goal": "Pripravi poročilo"}, s) == "single"


def test_explicit_mode_team_overrides_doc_guard():
    s = _settings()
    assert exec_mode.decide_exec_mode(
        {"kind": "autonomous", "goal": "Napiši poročilo", "mode": "team"}, s) == "team"
    assert exec_mode.decide_exec_mode(
        {"kind": "python", "team": "true", "goal": "Napiši poročilo"}, s) == "team"


def test_disabled_always_single():
    s = _settings(team_auto_enabled=False)
    assert exec_mode.decide_exec_mode({"kind": "autonomous", "goal": "x"}, s) == "single"


def test_empty_kinds_means_no_auto_team():
    s = _settings(team_auto_kinds="")
    assert exec_mode.decide_exec_mode({"kind": "autonomous", "goal": "x"}, s) == "single"


# ------------------------------------------------------------------ #
#  agenda.set_kind
# ------------------------------------------------------------------ #
def test_set_kind_changes_item(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "AGENDA_FILE", tmp_path / "agenda.json")
    item = ag.add(goal="Zgradi X", kind="build", target="x")
    assert ag.get(item["id"])["kind"] == "build"
    ag.set_kind(item["id"], "team")
    assert ag.get(item["id"])["kind"] == "team"


# ------------------------------------------------------------------ #
#  run_swarm: promocija kind → team pred dispatch
# ------------------------------------------------------------------ #
def test_process_items_promotes_autonomous_to_team(tmp_path, monkeypatch):
    import run_swarm
    monkeypatch.setattr(ag, "AGENDA_FILE", tmp_path / "agenda.json")
    item = ag.add(goal="Zgradi kompleksen modul X", kind="autonomous", target="x")

    calls = {"team": 0, "run": 0}
    monkeypatch.setattr(run_swarm.RobAIOrchestrator, "run_team",
                        lambda t, g: calls.__setitem__("team", calls["team"] + 1) or True)
    monkeypatch.setattr(run_swarm.RobAIOrchestrator, "run",
                        lambda t, g: calls.__setitem__("run", calls["run"] + 1) or True)

    res = run_swarm._process_items([ag.get(item["id"])])
    assert calls["team"] == 1 and calls["run"] == 0
    assert ag.get(item["id"])["kind"] == "team"   # promoviran v agendi
    assert res[0][1] is True


def test_process_items_keeps_python_as_single(tmp_path, monkeypatch):
    import run_swarm
    monkeypatch.setattr(ag, "AGENDA_FILE", tmp_path / "agenda.json")
    item = ag.add(goal="Enostavna naloga", kind="python", target="x")

    calls = {"team": 0, "run": 0}
    monkeypatch.setattr(run_swarm.RobAIOrchestrator, "run_team",
                        lambda t, g: calls.__setitem__("team", calls["team"] + 1) or True)
    monkeypatch.setattr(run_swarm.RobAIOrchestrator, "run",
                        lambda t, g: calls.__setitem__("run", calls["run"] + 1) or True)

    run_swarm._process_items([ag.get(item["id"])])
    assert calls["team"] == 0 and calls["run"] == 1
    assert ag.get(item["id"])["kind"] == "python"
