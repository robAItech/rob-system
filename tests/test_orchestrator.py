"""tests/test_orchestrator.py — C2: paden build enqueuje fix nalogo (wiring).

Preveri, da `_phase` ob neuspelem buildu pokliče `RunReviewer.maybe_enqueue_fix`
z run dict, ki vsebuje `last_traceback` (realen traceback za fix direktivo),
in da ob zelenem NE enqueuje. RSI veriga je mockana (brez LLM/Docker).
"""

from unittest import mock

from core.orchestrator import RobAIOrchestrator


def _fake_loopx_cls(ok, db_path, last_reason="", last_traceback=""):
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
    return _Fake


def _phase_with(fake_loopx_cls, reviewer):
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
        return RobAIOrchestrator._phase("fixdemo", "Popravi add", "implementacija")


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
