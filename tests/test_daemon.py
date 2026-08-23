"""Unit testi za core/daemon.py (P1 — avtonomni daemon).

Brez pravih zunanjih klicev (subprocess/LLM/Docker) — vse se mocka:
`subprocess.run`, `dev_cli` health, `MetaEvaluator`, `GoalProposer`.
Datoteke daemona/agende so usmerjene v tmp_path (nikoli realni .rob_ai).
"""

import json
import os
import sys
import types
from unittest import mock

import pytest

from core import agenda as ag
from core import audit as core_audit
from core import daemon


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Usmeri daemon/agenda/audit datoteke v tmp_path (izolacija od repo .rob_ai).
    STOP_FILE je modulna konstanta (ROB_AI/"daemon.stop") — BREZ tega patch-a bi
    test zapisal realni sentinel in ustavil živi daemon (se je zgodilo)."""
    monkeypatch.setattr(ag, "AGENDA_FILE", tmp_path / "agenda.json")
    monkeypatch.setattr(core_audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
    monkeypatch.setattr(daemon, "ROB_AI", tmp_path)
    monkeypatch.setattr(daemon, "DAEMON_FILE", tmp_path / "daemon.json")
    monkeypatch.setattr(daemon, "LOCK_FILE", tmp_path / "daemon.lock")
    monkeypatch.setattr(daemon, "STOP_FILE", tmp_path / "daemon.stop")
    monkeypatch.setattr(daemon, "DB_PATH", tmp_path / "memory.db")
    return tmp_path


def _settings(**overrides):
    """Lahek settings obj (brez realne .env) z DAEMON_* polji."""
    base = {
        "daemon_task_timeout_seconds": 0,
        "daemon_proxy_retry_seconds": 60,
        "daemon_heartbeat_seconds": 30,
        "daemon_idle_seconds": 5,
        "daemon_goal_pending_cap": 3,
        "daemon_goal_max_enqueue": 2,
        "daemon_consolidate_hours": 24,
        "daemon_reflect_hours": 168,
        "daemon_improve_hours": 168,
        "daemon_meta_check_hours": 168,
        "daemon_full_eval_hours": 168,
        "daemon_goal_hours": 6,
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


# ------------------------------------------------------------------ #
#  Lock
# ------------------------------------------------------------------ #
def test_lock_second_instance_fails(env):
    daemon._acquire_lock()
    try:
        with pytest.raises(RuntimeError, match="že teče"):
            daemon._acquire_lock()
    finally:
        daemon._release_lock()


def test_main_second_instance_exits_2(env):
    daemon._acquire_lock()
    try:
        assert daemon.main(["--once"]) == 2
    finally:
        daemon._release_lock()


def test_stale_lock_recovered(env, monkeypatch):
    # Lock z mrtvim PID → pobere se in nadomesti z lastnim PID.
    daemon.LOCK_FILE.write_text("999999999\n", encoding="utf-8")
    monkeypatch.setattr(daemon, "_lock_pid_alive", lambda pid: False)
    daemon._acquire_lock()
    assert daemon.LOCK_FILE.exists()
    assert int(daemon.LOCK_FILE.read_text(encoding="utf-8").strip()) == os.getpid()
    daemon._release_lock()


def test_lock_pid_alive_windows_probe(monkeypatch):
    # Windows: os.kill(pid, 0) ni probe (WinError 87) → OpenProcess.
    monkeypatch.setattr(daemon.os, "name", "nt")
    fake_ctypes = mock.Mock()
    kernel32 = fake_ctypes.windll.kernel32
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)
    # Mrtav PID → OpenProcess vrne 0 → False.
    kernel32.OpenProcess.return_value = 0
    assert daemon._lock_pid_alive(12345) is False
    # Živ PID → OpenProcess vrne ročico → True + CloseHandle.
    kernel32.OpenProcess.return_value = 999
    assert daemon._lock_pid_alive(12345) is True
    kernel32.CloseHandle.assert_called_once_with(999)


def test_cmd_stop_writes_sentinel(env, monkeypatch):
    daemon._write_heartbeat("idle")
    assert daemon._cmd_stop() == 0
    assert daemon.STOP_FILE.exists()
    data = json.loads(daemon.STOP_FILE.read_text(encoding="utf-8"))
    assert data["pid"] == os.getpid()


def test_run_loop_graceful_stop_via_sentinel(env, monkeypatch):
    # Zanka prebere stop sentinel → graceful shutdown (shutdown heartbeat,
    # release lock, return 0). Lovil bi UnboundLocalError (global _stop_requested).
    class _FakeStop:
        def unlink(self):
            pass
        def exists(self):
            return True
    monkeypatch.setattr(daemon, "STOP_FILE", _FakeStop())
    monkeypatch.setattr(daemon.dev_cli, "cmd_serve", mock.Mock(return_value=0))
    monkeypatch.setattr(daemon, "_proxy_ok", mock.Mock(return_value=True))
    rc = daemon.run_loop(_settings(), None)
    assert rc == 0
    assert not daemon.LOCK_FILE.exists()          # lock sproščen
    assert daemon._load_heartbeat()["state"] == "shutdown"


# ------------------------------------------------------------------ #
#  Recovery
# ------------------------------------------------------------------ #
def test_recover_marks_running_to_pending(env):
    it = ag.add("Naloga", kind="markdown", source="cli")
    ag.mark(it["id"], "running")
    n = daemon.recover_agenda()
    assert n == 1
    assert ag.get(it["id"])["status"] == "pending"


# ------------------------------------------------------------------ #
#  Scheduler
# ------------------------------------------------------------------ #
def _sched(due_ts):
    s = daemon.Scheduler()
    s.add("goal", lambda settings, cfg: {}, 3600)
    s.load_persisted({"goal": {"last_run": 0, "next_due": due_ts}})
    return s


def test_scheduler_due_when_next_due_passed():
    s = _sched(due_ts=100)
    assert s.due(100) is not None
    assert s.due(200) is not None


def test_scheduler_not_due_in_future():
    s = _sched(due_ts=200)
    assert s.due(100) is None


def test_scheduler_complete_advances_interval():
    s = _sched(due_ts=0)
    s.complete("goal", now=1000)
    assert s.due(1000 + 3599) is None
    assert s.due(1000 + 3600) is not None


def test_scheduler_warm_up_staggers(monkeypatch):
    # Prvi termin je sorazmeren intervalu (3600s → 3600//24 = 150s) + index*60.
    s = daemon.Scheduler()
    s.add("a", lambda settings, cfg: {}, 3600)
    s.add("b", lambda settings, cfg: {}, 3600)
    monkeypatch.setattr(daemon, "_now", lambda: 500)
    s.warm_up(500)
    # a dozori pri +150s (3600//24), b pri +150s + index*60 = +210s.
    assert s.due(500 + 149) is None
    assert s.due(500 + 150).get("name") == "a"
    assert s._jobs[1]["next_due"] == 500 + 210


def test_scheduler_warm_up_weekly_job_ne_firi_v_prvih_minutah(monkeypatch):
    # Tedenski job (168h) ob svežem boot-u ne sme biti na vrsti v prvi uri —
    # prvi termin je ~7h (interval//24), ne index+1 minut.
    s = daemon.Scheduler()
    s.add("weekly", lambda settings, cfg: {}, 168 * 3600)
    monkeypatch.setattr(daemon, "_now", lambda: 1000)
    s.warm_up(1000)
    assert s.due(1000 + 3600) is None                    # ni po 1h
    assert s.due(1000 + 7 * 3600).get("name") == "weekly"  # ~7h


# ------------------------------------------------------------------ #
#  decide (prioriteta: task > tick > idle)
# ------------------------------------------------------------------ #
def test_decide_task_priority_over_tick():
    s = _sched(due_ts=1)  # tick je na vrsti
    item = {"id": "x"}
    kind, payload = daemon.decide([item], s)
    assert kind == "task"
    assert payload is item


def test_decide_tick_when_no_pending():
    s = _sched(due_ts=1)
    kind, _payload = daemon.decide([], s)
    assert kind == "tick"


def test_decide_idle():
    s = _sched(due_ts=10 ** 12)
    kind, _ = daemon.decide([], s)
    assert kind == "idle"


# ------------------------------------------------------------------ #
#  Paralelni daemon — spawn / reap
# ------------------------------------------------------------------ #
class _FakePopen:
    def __init__(self, rc=0, done_after=1):
        self._rc = rc
        self._calls = 0
        self._done_after = done_after
        self.returncode = None
        self.killed = False
    def poll(self):
        if self.killed:
            return self.returncode   # ubit → reapan ob naslednjem pollu
        self._calls += 1
        if self._calls > self._done_after:
            self.returncode = self._rc
            return self._rc
        return None
    def kill(self):
        self.killed = True
        self.returncode = self._rc
        return None


def _entry(item, popen=None, settings=None):
    return {"item": item, "popen": popen or _FakePopen(),
            "started_at": int(__import__("time").time()), "deadline": None, "killed": False}


def test_spawn_task_uses_popen(env, monkeypatch):
    item = ag.add("Test naloga", kind="markdown", source="cli")
    fake_popen = _FakePopen()
    monkeypatch.setattr(daemon.subprocess, "Popen",
                        mock.Mock(return_value=fake_popen))
    entry = daemon._spawn_task(item, _settings(), None)
    call = daemon.subprocess.Popen.call_args
    assert "--item" in call.args[0] and item["id"] in call.args[0]
    assert entry["deadline"] is None   # timeout 0 → brez deadline
    entry2 = daemon._spawn_task(item, _settings(daemon_task_timeout_seconds=10), None)
    assert entry2["deadline"] is not None


def test_reap_task_success(env, monkeypatch):
    item = ag.add("Test naloga", kind="markdown", source="cli")
    ag.mark(item["id"], "done")   # child je označil done (simulacija)
    from core import meta_eval
    fake_me = mock.Mock()
    fake_me.snapshot.return_value = 42
    monkeypatch.setattr(meta_eval, "MetaEvaluator", lambda *a, **k: fake_me)
    popen = _FakePopen(rc=0, done_after=0)
    popen.poll()
    entry = _entry(item, popen=popen)
    res = daemon._reap_task(entry, _settings(), None, [entry])
    assert res["ok"] is True
    assert ag.get(item["id"])["status"] == "done"
    hb = daemon._load_heartbeat()
    assert hb["last_run_summary"]["ok"] is True
    assert hb["last_snapshot_id"] == 42


def test_reap_task_timeout_killed_marks_failed(env, monkeypatch):
    item = ag.add("Test naloga", kind="markdown", source="cli")
    ag.mark(item["id"], "running")   # child ni označil (ubit)
    from core import meta_eval
    monkeypatch.setattr(meta_eval, "MetaEvaluator",
                        lambda *a, **k: mock.Mock(snapshot=mock.Mock(return_value=1)))
    popen = _FakePopen(rc=1, done_after=0)
    popen.poll()
    entry = _entry(item, popen=popen)
    entry["killed"] = True
    res = daemon._reap_task(entry, _settings(), None, [entry])
    assert res["ok"] is False
    assert ag.get(item["id"])["status"] == "failed"
    log = (env / "audit.jsonl").read_text(encoding="utf-8")
    assert "timeout" in log


def test_reap_finished_reaps_completed_and_keeps_running(env, monkeypatch):
    done_item = ag.add("Done", kind="markdown", source="cli")
    run_item = ag.add("Running", kind="markdown", source="cli")
    from core import meta_eval
    monkeypatch.setattr(meta_eval, "MetaEvaluator",
                        lambda *a, **k: mock.Mock(snapshot=mock.Mock(return_value=1)))
    p_done = _FakePopen(rc=0, done_after=0)   # poll → 0 takoj
    p_run = _FakePopen(rc=0, done_after=999)  # poll → None (še teče)
    active = [_entry(done_item, popen=p_done), _entry(run_item, popen=p_run)]
    n = daemon._reap_finished(active, _settings(), None)
    assert n == 1
    assert len(active) == 1
    assert active[0]["item"]["id"] == run_item["id"]


def test_reap_finished_kills_timeout_then_reaps_failed(env, monkeypatch):
    item = ag.add("Timeout", kind="markdown", source="cli")
    ag.mark(item["id"], "running")
    from core import meta_eval
    monkeypatch.setattr(meta_eval, "MetaEvaluator",
                        lambda *a, **k: mock.Mock(snapshot=mock.Mock(return_value=1)))
    popen = _FakePopen(rc=1, done_after=999)
    entry = _entry(item, popen=popen)
    entry["deadline"] = int(__import__("time").time()) - 10   # pretečen
    active = [entry]
    # 1. poll: deadline pretečen → kill, ostane aktiven
    n = daemon._reap_finished(active, _settings(), None)
    assert n == 0 and len(active) == 1 and active[0]["killed"] is True
    # 2. poll: ubit → reapan → failed
    popen.returncode = 1
    n = daemon._reap_finished(active, _settings(), None)
    assert n == 1 and len(active) == 0
    assert ag.get(item["id"])["status"] == "failed"


def _mock_loop_deps(env, monkeypatch, popen):
    monkeypatch.setattr(daemon.dev_cli, "cmd_serve", mock.Mock(return_value=0))
    monkeypatch.setattr(daemon, "_proxy_ok", mock.Mock(return_value=True))
    from core import meta_eval
    monkeypatch.setattr(meta_eval, "MetaEvaluator",
                        lambda *a, **k: mock.Mock(snapshot=mock.Mock(return_value=1)))
    monkeypatch.setattr(daemon.subprocess, "Popen", mock.Mock(return_value=popen))


def test_run_loop_once_processes_one_task(env, monkeypatch):
    """--once: ena naloga spawn → reap → izhod (rc 0)."""
    item = ag.add("Test naloga", kind="markdown", source="cli")
    popen = _FakePopen(rc=0, done_after=0)
    _mock_loop_deps(env, monkeypatch, popen)
    rc = daemon.run_loop(_settings(daemon_workers=3), None, once=True)
    assert rc == 0
    assert daemon.subprocess.Popen.called
    call = daemon.subprocess.Popen.call_args
    assert "--item" in call.args[0] and item["id"] in call.args[0]
    # Naloga je bila obdelana (reap → last_run_summary). State je "shutdown" po izhodu.
    assert daemon._load_heartbeat()["last_run_summary"]["kind"] == "task"


def test_run_loop_stop_drains_active(env, monkeypatch):
    """Stop med aktivno nalogo → drain (reap) pred izhodom."""
    item = ag.add("Test naloga", kind="markdown", source="cli")
    # Fake Popen: ne konča takoj (poll → None nekaj časa), nato rc=0.
    popen = _FakePopen(rc=0, done_after=2)
    _mock_loop_deps(env, monkeypatch, popen)
    # Fake STOP: exists() postane True po 2 klicih → stop sredi naloge.
    class _FakeStop:
        def __init__(self):
            self.n = 0
        def unlink(self):
            pass
        def exists(self):
            self.n += 1
            return self.n > 1
    monkeypatch.setattr(daemon, "STOP_FILE", _FakeStop())
    rc = daemon.run_loop(_settings(), None)
    assert rc == 0
    # Aktivna naloga je bila reapan pred izhodom (last_run_summary prisotna).
    assert daemon._load_heartbeat()["last_run_summary"]["kind"] == "task"
    assert not daemon.LOCK_FILE.exists()   # lock sproščen


# ------------------------------------------------------------------ #
#  goal tick
# ------------------------------------------------------------------ #
def test_goal_tick_enqueues_build_only(env, monkeypatch):
    from core import goal_autonomy
    fake_proposer = mock.Mock()
    fake_proposer.propose.return_value = [
        {"goal": "Zmanjšaj neuspehe v projektu alpha", "action": "build", "project": "alpha"},
        {"goal": "Uglasi heal zanko (več poskusov)", "action": "tune", "project": None},
        {"goal": "Zmanjšaj neuspehe v projektu beta", "action": "build", "project": "beta"},
        {"goal": "Zmanjšaj neuspehe v projektu alpha", "action": "build", "project": "alpha"},  # dup
    ]
    monkeypatch.setattr(goal_autonomy, "GoalProposer", lambda *a, **k: fake_proposer)

    res = daemon._tick_goal(_settings(daemon_goal_max_enqueue=5), None)

    assert res["enqueued"] == 2  # alpha enkrat + beta; tune in dup preskočena
    goals = [g["goal"] for g in ag.all_()]
    assert "Zmanjšaj neuspehe v projektu alpha" in goals
    assert "Zmanjšaj neuspehe v projektu beta" in goals
    assert "Uglasi heal zanko (več poskusov)" not in goals
    assert all(g.get("source") == "goal_autonomy" for g in ag.all_())


def test_goal_tick_flood_guard(env, monkeypatch):
    from core import goal_autonomy
    fake_proposer = mock.Mock()
    monkeypatch.setattr(goal_autonomy, "GoalProposer", lambda *a, **k: fake_proposer)
    for i in range(3):
        ag.add(f"Naloga {i}", kind="markdown", source="cli")

    res = daemon._tick_goal(_settings(daemon_goal_pending_cap=3), None)

    assert res == {"enqueued": 0, "reason": "cap"}
    fake_proposer.propose.assert_not_called()


# ------------------------------------------------------------------ #
#  Heartbeat + storitve
# ------------------------------------------------------------------ #
def test_heartbeat_written(env):
    daemon._write_heartbeat("boot")
    hb = daemon._load_heartbeat()
    assert hb["state"] == "boot"
    assert hb["pid"] == os.getpid()


def test_heartbeat_none_pocisti_staro_polje(env):
    # Npr. crash sredi naloge → ob bootu se stale current_tasks počisti.
    daemon._write_heartbeat("running_task", current_tasks=[{"id": "x"}])
    daemon._write_heartbeat("boot", current_tasks=None)
    hb = daemon._load_heartbeat()
    assert "current_tasks" not in hb


def test_ensure_services_calls_cmd_serve(env, monkeypatch):
    monkeypatch.setattr(daemon.dev_cli, "cmd_serve", mock.Mock(return_value=0))
    monkeypatch.setattr(daemon, "_proxy_ok", mock.Mock(return_value=True))
    assert daemon._ensure_services(None) is True
    daemon.dev_cli.cmd_serve.assert_called_once()


def test_ensure_services_tolerates_cmd_serve_error(env, monkeypatch):
    monkeypatch.setattr(daemon.dev_cli, "cmd_serve",
                        mock.Mock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(daemon, "_proxy_ok", mock.Mock(return_value=False))
    assert daemon._ensure_services(None) is False  # daemon ne pade


# ------------------------------------------------------------------ #
#  Konfiguracija
# ------------------------------------------------------------------ #
def test_config_daemon_defaults():
    from core.config import SystemSettings
    s = SystemSettings(_env_file=None)
    assert s.daemon_idle_seconds == 5
    assert s.daemon_consolidate_hours == 24
    assert s.daemon_reflect_hours == 168
    assert s.daemon_goal_hours == 6
    assert s.daemon_goal_pending_cap == 3
    assert s.daemon_min_free_gb == 2.0
    assert s.daemon_task_timeout_seconds == 1800   # C/R: obešena naloga ne sme blokirati
    assert s.daemon_workers == 2                   # P-paralel: N sočasnih nalog


# ------------------------------------------------------------------ #
#  Agenda atomični zapis
# ------------------------------------------------------------------ #
def test_agenda_atomic_save(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "AGENDA_FILE", tmp_path / "agenda.json")
    for i in range(50):
        ag.add(f"Naloga {i}", kind="markdown", source="cli")
    items = ag.all_()
    assert len(items) == 50
    assert items[-1]["goal"] == "Naloga 49"
    # Datoteka je vedno veljaven JSON; ni temp ostankov.
    json.loads((tmp_path / "agenda.json").read_text(encoding="utf-8"))
    assert not (tmp_path / "agenda.json.tmp").exists()
