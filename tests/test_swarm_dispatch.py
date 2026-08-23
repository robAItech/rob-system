"""tests/test_swarm_dispatch.py — C2/SURGICAL: agenda dispatch v `_process_items`.

Fix naloge (source="fix_loop") gredo na `run_surgical` (s targeted test), ostali
na `run`/`run_autonomous`. Brez LLM/Docker — `RobAIOrchestrator` je mockan.
"""

from unittest import mock

import pytest

from core import agenda
from run_swarm import _process_items


@pytest.fixture
def iso(monkeypatch, tmp_path):
    monkeypatch.setattr(agenda, "AGENDA_FILE", tmp_path / "agenda.json")
    return agenda


def test_process_items_dispatches_fix_to_surgical(iso):
    item = agenda.add("fix calc", kind="python", target="calc",
                      source="fix_loop", test="test_add")
    fake_surgical = mock.Mock(return_value=True)
    with mock.patch("run_swarm.RobAIOrchestrator.run_surgical", fake_surgical):
        results = _process_items([item])

    fake_surgical.assert_called_once_with("calc", "fix calc", target_test="test_add")
    assert agenda.get(item["id"])["status"] == "done"
    assert results == [(item["id"], True)]


def test_process_items_other_sources_use_run(iso):
    item = agenda.add("build modul", kind="python", target="calc", source="dashboard")
    fake_run = mock.Mock(return_value=True)
    with mock.patch("run_swarm.RobAIOrchestrator.run", fake_run):
        results = _process_items([item])

    fake_run.assert_called_once_with("calc", "build modul")
    assert results == [(item["id"], True)]


def test_process_items_autonomous_kind_uses_run_autonomous(iso):
    item = agenda.add("avtonomna naloga", kind="autonomous", target="calc", source="cli")
    fake_auto = mock.Mock(return_value=True)
    with mock.patch("run_swarm.RobAIOrchestrator.run_autonomous", fake_auto):
        results = _process_items([item])

    fake_auto.assert_called_once_with("calc", "avtonomna naloga")
    assert results == [(item["id"], True)]


def test_process_items_modify_kind_uses_run_modify(iso):
    """MODIFY — kind='modify' → run_modify (false-green guard)."""
    item = agenda.add("izboljšaj modul", kind="modify", target="calc", source="cli")
    fake_modify = mock.Mock(return_value=True)
    with mock.patch("run_swarm.RobAIOrchestrator.run_modify", fake_modify):
        results = _process_items([item])

    fake_modify.assert_called_once_with("calc", "izboljšaj modul")
    assert results == [(item["id"], True)]


def test_process_items_failure_marks_failed(iso):
    item = agenda.add("build modul", kind="python", target="calc", source="cli")
    with mock.patch("run_swarm.RobAIOrchestrator.run", mock.Mock(return_value=False)):
        results = _process_items([item])

    assert agenda.get(item["id"])["status"] == "failed"
    assert results == [(item["id"], False)]
