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
