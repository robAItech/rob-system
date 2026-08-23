"""tests/test_orchestrator.py — C2: paden build enqueuje fix nalogo (wiring).

Preveri, da `_phase` ob neuspelem buildu pokliče `RunReviewer.maybe_enqueue_fix`
z run dict, ki vsebuje `last_traceback` (realen traceback za fix direktivo),
in da ob zelenem NE enqueuje. RSI veriga je mockana (brez LLM/Docker).
"""

from unittest import mock

from core.orchestrator import RobAIOrchestrator


def _fake_loopx_cls(ok, db_path, last_reason="", last_traceback="", changed=True):
    class _Fake:
        _detect_kind = staticmethod(lambda goal: "python")
        def __init__(self, project):
            self.project = project
            self.gbrain = mock.Mock(db_path=db_path)
            self.last_reason = last_reason
            self.last_traceback = last_traceback
            self.llm_calls = 2
            self.max_attempts = 5
        def execute_and_heal(self, directive, spec_hint=""):
            return ok
        def _module_changed(self):
            return changed
    return _Fake


def _phase_with(fake_loopx_cls, reviewer, require_change=False):
    with mock.patch("core.orchestrator.GBrainBridge",
                    return_value=mock.Mock(get_blacklists=lambda p: [])), \
         mock.patch("core.orchestrator.GraphifyBridge",
                    return_value=mock.Mock(build_code_graph=lambda: None,
                                           render_context=lambda p: "")), \
         mock.patch("core.orchestrator.GSTACKArchitectBridge",
                    return_value=mock.Mock(generate_manifest=lambda p, d: {},
                                           render_spec_hint=lambda m: "")), \
         mock.patch("core.orchestrator.HermesBuilderBridge",
                    return_value=mock.Mock(write_initial_stubs_if_missing=lambda: None)), \
         mock.patch("core.orchestrator.LoopXEngineBridge", fake_loopx_cls), \
         mock.patch("core.run_review.RunReviewer", return_value=reviewer):
        return RobAIOrchestrator._phase("fixdemo", "Popravi add", "implementacija",
                                        require_change=require_change)


def test_failed_phase_enqueues_fix_task(tmp_path):
    db = tmp_path / "memory.db"
    reviewer = mock.Mock()
    reviewer.review.return_value = {"outcome": "failed", "root_cause": "recurring_error",
                                    "next_step": "change_approach", "next_step_hint": "h",
                                    "lesson": "lekcija"}
    ok = _phase_with(
        _fake_loopx_cls(False, db,
                        last_reason="ista napaka ValueError",
                        last_traceback='File "test_add.py", line 3, in test_add\nValueError: bad'),
        reviewer)

    assert ok is False
    reviewer.maybe_enqueue_fix.assert_called_once()
    run = reviewer.maybe_enqueue_fix.call_args[0][0]
    assert run["project"] == "fixdemo"
    assert run["task_type"] == "python"
    assert run["last_traceback"] == 'File "test_add.py", line 3, in test_add\nValueError: bad'


def test_green_phase_does_not_enqueue_fix(tmp_path):
    db = tmp_path / "memory.db"
    reviewer = mock.Mock()
    reviewer.review.return_value = {"outcome": "green", "root_cause": "correct"}
    ok = _phase_with(_fake_loopx_cls(True, db), reviewer)

    assert ok is True
    reviewer.maybe_enqueue_fix.assert_not_called()


# --------------------------------------------------------------------------- #
#  SURGICAL FIX — run_surgical (skip gstack/hermes, targeted)
# --------------------------------------------------------------------------- #

def _surgical_module(tmp_path, monkeypatch):
    from pathlib import Path
    # run_surgical uporablja Path("actions/<proj>") relativno na cwd → chdir v tmp.
    monkeypatch.chdir(tmp_path)
    mod = Path("actions/surgical_proj")
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "main.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    return mod


def _run_surgical_with(fake_loopx, reviewer):
    from pathlib import Path
    from core.orchestrator import RobAIOrchestrator
    with mock.patch("core.orchestrator.LoopXEngineBridge", return_value=fake_loopx), \
         mock.patch("core.orchestrator.GBrainBridge",
                    return_value=mock.Mock(get_blacklists=lambda p: [])), \
         mock.patch("core.orchestrator.GraphifyBridge",
                    return_value=mock.Mock(build_code_graph=lambda: None)), \
         mock.patch("core.orchestrator.GSTACKArchitectBridge", return_value=mock.Mock()) as gstack, \
         mock.patch("core.orchestrator.HermesBuilderBridge", return_value=mock.Mock()) as hermes, \
         mock.patch("core.run_review.RunReviewer", return_value=reviewer):
        ok = RobAIOrchestrator.run_surgical("surgical_proj", "Popravi add", target_test="test_add")
    return ok, gstack, hermes


def test_run_surgical_skips_gstack_hermes_and_sets_flags(tmp_path, monkeypatch):
    _surgical_module(tmp_path, monkeypatch)
    fake_loopx = mock.Mock()
    fake_loopx.execute_and_heal.return_value = True
    fake_loopx.last_reason = ""
    fake_loopx.last_traceback = ""
    fake_loopx.llm_calls = 1
    fake_loopx.max_attempts = 5
    fake_loopx.gbrain = mock.Mock(db_path=tmp_path / "memory.db")
    reviewer = mock.Mock(review=mock.Mock(return_value=None))

    ok, gstack, hermes = _run_surgical_with(fake_loopx, reviewer)

    assert ok is True
    fake_loopx.execute_and_heal.assert_called_once_with("Popravi add", spec_hint="")
    assert fake_loopx.surgical is True          # LoopX v surgical načinu
    assert fake_loopx.target_test == "test_add"
    gstack.return_value.generate_manifest.assert_not_called()   # brez re-scaffolda
    hermes.return_value.write_initial_stubs_if_missing.assert_not_called()


def test_run_surgical_failed_enqueues_fix(tmp_path, monkeypatch):
    _surgical_module(tmp_path, monkeypatch)
    fake_loopx = mock.Mock()
    fake_loopx.execute_and_heal.return_value = False
    fake_loopx.last_reason = "ista napaka ValueError"
    fake_loopx.last_traceback = 'File "test_add.py", line 3, in test_add\nValueError: bad'
    fake_loopx.llm_calls = 2
    fake_loopx.max_attempts = 5
    fake_loopx.gbrain = mock.Mock(db_path=tmp_path / "memory.db")
    reviewer = mock.Mock()
    reviewer.review.return_value = {"outcome": "failed", "root_cause": "recurring_error",
                                    "next_step": "change_approach", "next_step_hint": "h",
                                    "lesson": "lekcija"}

    ok, _g, _h = _run_surgical_with(fake_loopx, reviewer)

    assert ok is False
    reviewer.maybe_enqueue_fix.assert_called_once()
    run = reviewer.maybe_enqueue_fix.call_args[0][0]
    assert run["last_traceback"] == 'File "test_add.py", line 3, in test_add\nValueError: bad'


def test_run_surgical_missing_module_falls_back_to_phase(tmp_path):
    # target nima .py → fallback na _phase (ne crash, ni surgical)
    from core.orchestrator import RobAIOrchestrator
    with mock.patch("core.orchestrator.RobAIOrchestrator._phase", return_value=True) as phase:
        ok = RobAIOrchestrator.run_surgical("nonexistent_proj", "Popravi", target_test="test_x")
    assert ok is True
    phase.assert_called_once()


# --------------------------------------------------------------------------- #
#  MODIFY — false-green guard (zahteva dejansko spremembo)
# --------------------------------------------------------------------------- #

def test_phase_require_change_false_green(tmp_path):
    """MODIFY — build zelen, a modul nespremenjen → FALSE GREEN (neuspeh)."""
    db = tmp_path / "memory.db"
    reviewer = mock.Mock()
    reviewer.review.return_value = {"outcome": "failed", "root_cause": "recurring_error",
                                    "next_step": "change_approach", "next_step_hint": "h",
                                    "lesson": "lekcija"}
    ok = _phase_with(_fake_loopx_cls(True, db, changed=False), reviewer, require_change=True)
    assert ok is False
    # review dobi outcome=failed (ne zelen)
    run = reviewer.review.call_args[0][0]
    assert run["outcome"] == "failed"


def test_phase_require_change_change_made(tmp_path):
    """MODIFY — build zelen IN modul spremenjen → uspeh."""
    db = tmp_path / "memory.db"
    reviewer = mock.Mock()
    reviewer.review.return_value = {"outcome": "green", "root_cause": "correct"}
    ok = _phase_with(_fake_loopx_cls(True, db, changed=True), reviewer, require_change=True)
    assert ok is True
    run = reviewer.review.call_args[0][0]
    assert run["outcome"] == "green"


def test_required_test_files_parser():
    from core.orchestrator import RobAIOrchestrator
    assert RobAIOrchestrator._required_test_files(
        "dodaj test_truncate_start.py, ne spreminjaj test_truncate_text.py") == \
        ["test_truncate_start.py", "test_truncate_text.py"]
    assert RobAIOrchestrator._required_test_files("izboljšaj modul") == []


def test_run_modify_passes_required_test_files(tmp_path):
    """MODIFY — run_modify iz direktive izvleče test file in ga posreduje _phase."""
    from core.orchestrator import RobAIOrchestrator
    with mock.patch("core.orchestrator.RobAIOrchestrator._phase", return_value=True) as phase:
        ok = RobAIOrchestrator.run_modify("m", "dodaj funkcijo X, nov test file test_new.py")
    assert ok is True
    kwargs = phase.call_args[1]
    assert kwargs["require_change"] is True
    assert kwargs["required_files"] == ["test_new.py"]


def test_run_modify_false_green(tmp_path, monkeypatch):
    """MODIFY end-to-end (mock pipeline): zelen + _module_changed False → False."""
    _surgical_module(tmp_path, monkeypatch)
    fake_loopx = mock.Mock()
    fake_loopx.execute_and_heal.return_value = True
    fake_loopx._module_changed.return_value = False
    fake_loopx.last_reason = ""
    fake_loopx.last_traceback = ""
    fake_loopx.llm_calls = 1
    fake_loopx.max_attempts = 5
    fake_loopx.gbrain = mock.Mock(db_path=tmp_path / "memory.db")
    reviewer = mock.Mock()
    reviewer.review.return_value = {"outcome": "failed", "root_cause": "recurring_error",
                                    "next_step": "change_approach", "next_step_hint": "h",
                                    "lesson": "x"}
    from core.orchestrator import RobAIOrchestrator
    with mock.patch("core.orchestrator.LoopXEngineBridge", return_value=fake_loopx), \
         mock.patch("core.orchestrator.GBrainBridge",
                    return_value=mock.Mock(get_blacklists=lambda p: [])), \
         mock.patch("core.orchestrator.GraphifyBridge",
                    return_value=mock.Mock(build_code_graph=lambda: None)), \
         mock.patch("core.run_review.RunReviewer", return_value=reviewer):
        ok = RobAIOrchestrator.run_modify("surgical_proj", "Izboljšaj modul")
    assert ok is False


# --------------------------------------------------------------------------- #
#  AGENTI v daemonu — run_team / run_fork / run_plan
# --------------------------------------------------------------------------- #

def test_run_team(mock_agents=None):
    """Z6 — run_team: built + verdict ok → True; verdict ne-ok → False."""
    from core.orchestrator import RobAIOrchestrator
    with mock.patch("core.team.TeamCoordinator") as tc:
        tc.return_value.run.return_value = {
            "built": True, "severity": "low", "verdict": {"ok": True}}
        assert RobAIOrchestrator.run_team("p", "g") is True
    with mock.patch("core.team.TeamCoordinator") as tc:
        tc.return_value.run.return_value = {
            "built": True, "severity": "high", "verdict": {"ok": False}}
        assert RobAIOrchestrator.run_team("p", "g") is False


def test_run_fork():
    """Z8 — run_fork: explore_and_run izvede najboljšo varianto."""
    from core.orchestrator import RobAIOrchestrator
    with mock.patch("core.fork.Explorer") as ex:
        ex.return_value.explore_and_run.return_value = {
            "variants": 3, "executed": True}
        assert RobAIOrchestrator.run_fork("p", "g") is True
    with mock.patch("core.fork.Explorer") as ex:
        ex.return_value.explore_and_run.return_value = {
            "variants": 3, "executed": False}
        assert RobAIOrchestrator.run_fork("p", "g") is False


def test_run_plan(tmp_path, monkeypatch):
    """Z5 — run_plan: dekompozicija → podnaloge v agendo (distinktni targeti)."""
    from core import agenda
    monkeypatch.setattr(agenda, "AGENDA_FILE", tmp_path / "agenda.json")
    from core.orchestrator import RobAIOrchestrator
    with mock.patch("core.task_planner.TaskPlanner") as tp:
        tp.return_value.decompose.return_value = ["korak 1", "korak 2"]
        assert RobAIOrchestrator.run_plan("biggoal", "velik cilj") is True
    targets = [x["target"] for x in agenda.all_()]
    assert targets == ["biggoal__s1", "biggoal__s2"]
    assert all(x["kind"] == "python" for x in agenda.all_())
    assert all(x["source"] == "plan_subtask" for x in agenda.all_())
