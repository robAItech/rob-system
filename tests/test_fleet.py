"""P9 — fleet master–worker: server enota, agenda lease, client roundtrip.

Brez pravih omrežnih klicev: server se testira prek TestClient, client pa prek
monkeypatch-a `requests.post` na TestClient (roundtrip v enem procesu, dve
"mapi" — master agendo + workerjevo senčno agendo).
"""

import json
import time

import pytest
from fastapi.testclient import TestClient

import core.agenda as agenda
from core import audit, fleet, memory_sync


H = {"Authorization": "Bearer test-token"}


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Agenda + fleet workers + memory.db v začasni mapi (izven .rob_ai).

    Hermetično: testi ne smejo odvisni od obstoječega .rob_ai (CI nima
    memory.db) — drugače /fleet/status pade kot "no such table" samo v CI."""
    monkeypatch.setattr(agenda, "AGENDA_FILE", tmp_path / "agenda.json")
    monkeypatch.setattr(fleet, "FLEET_WORKERS_FILE", tmp_path / "fleet_workers.json")
    monkeypatch.setattr(memory_sync, "DEFAULT_DB", tmp_path / "mem.db")
    monkeypatch.setattr(audit, "AUDIT_FILE", tmp_path / "audit.jsonl")   # testi ne pišejo v pravi audit
    return tmp_path


@pytest.fixture
def client(tmp_state):
    return TestClient(fleet.create_app(token="test-token"))


def _add_pending(n=1, prefix="naloga"):
    return [agenda.add(f"{prefix}-{i}", kind="python", target=f"mod{prefix}-{i}")
            for i in range(n)]


class TestFleetServer:
    def test_claim_vrne_pending_in_mark_running(self, client):
        _add_pending(1)
        r = client.post("/fleet/claim", json={"worker": "worker-a"}, headers=H)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "running"
        assert items[0]["claimed_by"] == "worker-a"
        assert agenda.pending() == []   # ni več pending → lokalni claim je ne vzame

    def test_claim_prazna_vrsta(self, client):
        r = client.post("/fleet/claim", json={"worker": "w"}, headers=H)
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_claim_ne_duplicira_running(self, client):
        _add_pending(2)
        c1 = client.post("/fleet/claim", json={"worker": "w1"}, headers=H).json()["items"]
        c2 = client.post("/fleet/claim", json={"worker": "w2"}, headers=H).json()["items"]
        assert len(c1) == 1 and len(c2) == 1
        assert c1[0]["id"] != c2[0]["id"]

    def test_auth_fail_closed(self, client):
        r = client.post("/fleet/claim", json={"worker": "w"})
        assert r.status_code == 401
        r = client.post("/fleet/claim", json={"worker": "w"},
                        headers={"Authorization": "Bearer wrong-token"})
        assert r.status_code == 401

    def test_result_done(self, client):
        item = _add_pending(1)[0]
        client.post("/fleet/claim", json={"worker": "w1"}, headers=H)
        r = client.post("/fleet/result",
                        json={"item_id": item["id"], "ok": True,
                              "target": item["target"], "worker": "w1",
                              "detail": "vse zeleno", "duration_s": 12.5},
                        headers=H)
        assert r.status_code == 200
        got = agenda.get(item["id"])
        assert got["status"] == "done"
        assert got["result_worker"] == "w1"
        assert got["duration_s"] == 12.5

    def test_result_failed(self, client):
        item = _add_pending(1)[0]
        client.post("/fleet/claim", json={"worker": "w1"}, headers=H)
        client.post("/fleet/result", json={"item_id": item["id"], "ok": False,
                                           "target": item["target"]}, headers=H)
        assert agenda.get(item["id"])["status"] == "failed"

    def test_lease_sprosti_mrtvega_workerja(self, client):
        _add_pending(1)
        client.post("/fleet/claim", json={"worker": "w1"}, headers=H)
        # postaraj, da je claim prestar (worker umrl sredi naloge)
        items = agenda.all_()
        items[0]["claimed_at"] = int(time.time()) - 99999
        agenda._save(items)
        r = client.post("/fleet/claim", json={"worker": "w2"}, headers=H)
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["claimed_by"] == "w2"

    def test_heartbeat_worker_viden(self, client):
        r = client.post("/fleet/heartbeat",
                        json={"worker": "w1", "tasks": [{"id": "x", "goal": "g"}]},
                        headers=H)
        assert r.status_code == 200
        workers = fleet._load_workers()
        assert "w1" in workers
        assert workers["w1"]["last_seen"] > 0

    def test_status(self, client):
        _add_pending(2)
        r = client.get("/fleet/status", headers=H)
        assert r.status_code == 200
        assert r.json()["agenda"]["pending"] == 2

    def test_claim_pise_audit(self, client, tmp_state):
        _add_pending(1)
        client.post("/fleet/claim", json={"worker": "w1"}, headers=H)
        txt = (tmp_state / "audit.jsonl").read_text(encoding="utf-8")
        assert "fleet-claim" in txt
        assert "w1" in txt

    def test_result_pise_audit(self, client, tmp_state):
        item = _add_pending(1)[0]
        client.post("/fleet/claim", json={"worker": "w1"}, headers=H)
        client.post("/fleet/result",
                    json={"item_id": item["id"], "ok": True, "target": item["target"]},
                    headers=H)
        txt = (tmp_state / "audit.jsonl").read_text(encoding="utf-8")
        assert "fleet-result" in txt


class TestFleetAgenda:
    def test_claim_fleet_razlicni_targeti(self, tmp_state):
        _add_pending(3)
        got = agenda.claim_fleet(limit=3, worker="w1")
        assert len(got) == 3
        assert len({i["target"] for i in got}) == 3

    def test_upsert_fleet_skrije_pred_lokalnim_claimom(self, tmp_state):
        item = _add_pending(1)[0]
        item["fleet_claimed"] = True
        item["status"] = "running"
        agenda.upsert_fleet(item)
        assert agenda.claim_pending() == []   # running ni pending → ni podvajanja

    def test_release_ne_dotika_lokalnih_running(self, tmp_state):
        item = _add_pending(1)[0]
        agenda.mark(item["id"], "running")    # lokalni running (brez claimed_at)
        assert agenda.release_expired_claims(10) == 0


class TestFleetClient:
    def test_claim_roundtrip(self, client, tmp_state, monkeypatch):
        import requests
        _add_pending(1)
        real_post = requests.post

        def fake_post(url, json=None, headers=None, timeout=None):
            path = url.split("/fleet")[1]
            r = client.post(f"/fleet{path}", json=json, headers=headers)

            class _R:
                def raise_for_status(self):
                    if r.status_code >= 400:
                        raise RuntimeError(f"HTTP {r.status_code}")
                def json(self):
                    return r.json()
            return _R()

        monkeypatch.setattr(requests, "post", fake_post)
        c = fleet.FleetClient("http://master:8789", "test-token")
        item = c.claim(worker="worker-x")
        assert item is not None
        assert item["status"] == "running"
        assert item["claimed_by"] == "worker-x"
        # preveri, da fake_post dejansko ni šel na pravo omrežje
        assert requests.post is not real_post


class TestFleetDaemonTicks:
    """Periodični sync: worker memory tick + master backup tick."""

    def test_tick_fleet_memory_pull_in_push(self, monkeypatch):
        from core import daemon
        calls = []
        monkeypatch.setattr(daemon, "_fleet_pull_memory",
                            lambda s: calls.append("pull") or {"a": 1})
        monkeypatch.setattr(daemon, "_fleet_push_memory",
                            lambda s: calls.append("push") or {"a": 0})
        r = daemon._tick_fleet_memory(object(), None)
        assert calls == ["pull", "push"]
        assert r["pulled"] == {"a": 1}

    def test_tick_fleet_backup_ok(self, monkeypatch):
        from core import daemon, fleet
        monkeypatch.setattr(fleet, "_cmd_backup", lambda: 0)
        assert daemon._tick_fleet_backup(object(), None)["backup"] == "ok"

    def test_tick_fleet_backup_napaka(self, monkeypatch):
        from core import daemon, fleet
        monkeypatch.setattr(daemon, "_append_error", lambda msg: None)

        def boom():
            raise RuntimeError("git dol")
        monkeypatch.setattr(fleet, "_cmd_backup", boom)
        r = daemon._tick_fleet_backup(object(), None)
        assert "napaka" in r["backup"]

    def test_build_scheduler_fleet_jobi(self):
        from core import daemon

        class S:
            daemon_consolidate_hours = 24
            daemon_reflect_hours = 168
            daemon_improve_hours = 168
            daemon_meta_check_hours = 168
            daemon_full_eval_hours = 0
            daemon_goal_hours = 6
            fleet_role = "worker"
            fleet_sync_memory = True
            fleet_memory_sync_seconds = 60
            fleet_backup_seconds = 3600

        s = S()
        names = set(daemon.build_scheduler(s).to_dict().keys())
        assert "fleet_memory" in names
        assert "goal" not in names          # worker nima goal ticka

        s2 = S(); s2.fleet_role = "master"
        names2 = set(daemon.build_scheduler(s2).to_dict().keys())
        assert "fleet_backup" in names2
        assert "goal" in names2
        assert "fleet_memory" not in names2   # master ne potiska spomina workerju

    def test_fleet_backoff_skips_claim_ko_offline(self, monkeypatch):
        """Master nedosegljiv → worker NE išče povezave (backoff aktiven)."""
        from core import daemon
        monkeypatch.setattr(daemon, "_fleet_offline_until", time.time() + 999)
        calls = []
        monkeypatch.setattr(fleet, "FleetClient", lambda *a, **k: calls.append("net") or None)
        assert daemon._fleet_claim_remote(object()) == []
        assert calls == []   # med backoff-om ni omrežnega klica

    def test_fleet_mark_offline_online(self, monkeypatch):
        from core import daemon

        class S:
            fleet_backoff_seconds = 60
        daemon._fleet_mark_offline(S())
        assert daemon._fleet_offline() is True
        daemon._fleet_mark_online()
        assert daemon._fleet_offline() is False

    def test_fleet_claim_remote_online_zapise_sencno(self, tmp_state, monkeypatch):
        """Worker claim-a nalogo od masterja → zapiše v lokalno senčno agendo."""
        from core import daemon

        class FakeClient:
            def __init__(self, *a, **k):
                pass
            def claim(self, worker=None):
                return {"id": "abc", "target": "mod1", "goal": "g", "status": "pending"}

        monkeypatch.setattr(daemon, "_fleet_offline_until", 0.0)
        monkeypatch.setattr(fleet, "FleetClient", FakeClient)

        class S:
            fleet_master_url = "http://x"
            fleet_token = "t"
            fleet_backoff_seconds = 60
        res = daemon._fleet_claim_remote(S())
        assert len(res) == 1
        assert res[0]["fleet_claimed"] is True
        assert res[0]["status"] == "running"
        assert any(i.get("target") == "mod1" for i in agenda.all_())   # senčna agenda

    def test_fleet_claim_remote_offline_brez_omrezja(self, monkeypatch):
        from core import daemon
        monkeypatch.setattr(daemon, "_fleet_offline_until", time.time() + 999)
        calls = []
        monkeypatch.setattr(fleet, "FleetClient", lambda *a, **k: calls.append(1) or None)

        class S:
            pass
        assert daemon._fleet_claim_remote(S()) == []
        assert calls == []

    def test_fleet_push_actions_poslje_modul(self, monkeypatch):
        """Worker po build-u pošlje modul masterju prek HTTP."""
        from core import daemon
        pushed = {}

        class FakeClient:
            def __init__(self, *a, **k):
                pass
            def push_actions(self, module, files):
                pushed["module"] = module
                pushed["files"] = files

        monkeypatch.setattr(daemon, "_fleet_offline_until", 0.0)
        monkeypatch.setattr(fleet, "FleetClient", FakeClient)
        monkeypatch.setattr(fleet, "export_module_files", lambda m: {"main.py": "x=1"})

        class S:
            fleet_master_url = "http://x"
            fleet_token = "t"
            fleet_backoff_seconds = 60
        daemon._fleet_push_actions(S(), "mod1")
        assert pushed == {"module": "mod1", "files": {"main.py": "x=1"}}


class TestFleetActions:
    """Prenos zgrajenih modulov worker → master prek HTTP (brez gita)."""

    @pytest.fixture
    def act_client(self, tmp_state, monkeypatch, tmp_path):
        monkeypatch.setattr(fleet, "PROJECT_ROOT", tmp_path)   # piši v tmp, ne v repo
        return TestClient(fleet.create_app(token="test-token"))

    def test_push_actions_zapise_datoteke(self, act_client, tmp_path):
        r = act_client.post("/fleet/actions",
                            json={"module": "mymod",
                                  "files": {"__init__.py": "", "main.py": "print(1)"}},
                            headers=H)
        assert r.status_code == 200
        assert r.json()["files"] == 2
        assert (tmp_path / "actions" / "mymod" / "main.py").read_text() == "print(1)"

    def test_push_actions_path_traversal(self, act_client):
        r = act_client.post("/fleet/actions",
                            json={"module": "mymod", "files": {"../evil.py": "x"}},
                            headers=H)
        assert r.status_code == 400

    def test_push_actions_bad_module(self, act_client):
        r = act_client.post("/fleet/actions",
                            json={"module": "../../etc", "files": {"a.py": "x"}},
                            headers=H)
        assert r.status_code == 400

    def test_push_actions_zahteva_auth(self, act_client):
        r = act_client.post("/fleet/actions", json={"module": "m", "files": {}})
        assert r.status_code == 401

    def test_export_module_files(self, tmp_state, monkeypatch, tmp_path):
        monkeypatch.setattr(fleet, "PROJECT_ROOT", tmp_path)
        (tmp_path / "actions" / "mod" / "sub").mkdir(parents=True)
        (tmp_path / "actions" / "mod" / "main.py").write_text("x=1", encoding="utf-8")
        (tmp_path / "actions" / "mod" / "sub" / "util.py").write_text("y=2", encoding="utf-8")
        (tmp_path / "actions" / "mod" / "__pycache__").mkdir()
        (tmp_path / "actions" / "mod" / "__pycache__" / "main.cpython-311.pyc").write_bytes(b"bin")
        files = fleet.export_module_files("mod")
        assert set(files) == {"main.py", "sub/util.py"}


class TestFleetBackupRestore:
    """Backup/restore (izvoz spomina+agende v git) — git se mock-a."""

    def _patch_root(self, monkeypatch, tmp_path):
        """PROJECT_ROOT in BACKUP_FILE na tmp (BACKUP_FILE je module konstanta)."""
        monkeypatch.setattr(fleet, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(fleet, "BACKUP_FILE", tmp_path / "fleet" / "backup.json")


    def _mk_git(self, monkeypatch, calls, diff_rc=1):
        def fake_call(cmd, **kw):
            calls.append(list(cmd))
            if list(cmd)[:2] == ["git", "diff"]:
                return diff_rc   # 0 = ni sprememb, 1 = so spremembe
            return 0
        monkeypatch.setattr(fleet.subprocess, "call", fake_call)

    def test_backup_commita_in_pusha(self, tmp_state, monkeypatch, tmp_path):
        self._patch_root(monkeypatch, tmp_path)
        calls = []
        self._mk_git(monkeypatch, calls, diff_rc=1)
        agenda.add("backup naloga", target="bk1")
        rc = fleet._cmd_backup()
        assert rc == 0
        bf = tmp_path / "fleet" / "backup.json"
        assert bf.exists()
        data = json.loads(bf.read_text(encoding="utf-8"))
        assert any(i.get("target") == "bk1" for i in data["agenda"])
        assert "memory" in data and "tables" in data["memory"]
        gits = [c for c in calls if c[0] == "git"]
        assert any(c[1] == "add" for c in gits)
        assert any(c[1] == "commit" for c in gits)
        assert any(c == ["git", "push"] for c in gits)

    def test_backup_brez_sprememb_brez_commita(self, tmp_state, monkeypatch, tmp_path):
        self._patch_root(monkeypatch, tmp_path)
        calls = []
        self._mk_git(monkeypatch, calls, diff_rc=0)
        assert fleet._cmd_backup() == 0
        assert not any(c[1] == "commit" for c in calls)

    def test_backup_git_add_napaka(self, tmp_state, monkeypatch, tmp_path):
        def bad_add(cmd, **kw):
            return 1 if list(cmd)[:2] == ["git", "add"] else 0
        monkeypatch.setattr(fleet.subprocess, "call", bad_add)
        self._patch_root(monkeypatch, tmp_path)
        assert fleet._cmd_backup() == 1

    def test_restore_zdruzi_spomin_in_agendo(self, tmp_state, monkeypatch, tmp_path):
        self._patch_root(monkeypatch, tmp_path)
        payload = {
            "memory": {"tables": {"semantic_memories": [
                {"theme": "r-tema", "project": "p", "content": "lekcija", "kind": "principle"}]},
                "exported_at": 1},
            "agenda": [{"id": "x1", "goal": "restore naloga", "target": "restore_mod", "status": "pending"}],
            "backed_up_at": int(time.time()),
        }
        (tmp_path / "fleet").mkdir(parents=True, exist_ok=True)
        (tmp_path / "fleet" / "backup.json").write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(fleet.subprocess, "call", lambda *a, **k: 0)
        rc = fleet._cmd_restore()
        assert rc == 0
        assert memory_sync.count_memory()["semantic_memories"] >= 1
        assert any(i.get("target") == "restore_mod" for i in agenda.all_())

    def test_restore_brez_backupa(self, tmp_state, monkeypatch, tmp_path):
        self._patch_root(monkeypatch, tmp_path)
        monkeypatch.setattr(fleet.subprocess, "call", lambda *a, **k: 0)
        assert fleet._cmd_restore() == 1
