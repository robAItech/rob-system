"""P9 faza 4 — deljen spomin: izvoz/združitev učnih tabel + fleet memory endpointi.

Brez pravih omrežnih klicev: endpointi prek TestClient, izvoz/merge na začasnih
memory.db (GBrainBridge ustvari shemo).
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

import core.agenda as agenda
from core import audit, fleet, memory_sync
from core.gbrain_bridge import GBrainBridge


@pytest.fixture
def mem_db(tmp_path):
    db = tmp_path / "mem.db"
    GBrainBridge(db)   # ustvari shemo memory.db
    return db


def _insert(db, table, **cols):
    with sqlite3.connect(db) as c:
        memory_sync._ensure_schema(c)   # tabela obstaja tudi na sveži DB
        c.execute(f"INSERT INTO {table} ({','.join(cols)}) "
                  f"VALUES ({','.join('?' * len(cols))})", list(cols.values()))


class TestMemorySync:
    def test_export_vse_tabele_brez_id(self, mem_db):
        _insert(mem_db, "semantic_memories", theme="t", content="c1", kind="principle")
        payload = memory_sync.export_memory(mem_db)
        assert "semantic_memories" in payload["tables"]
        rows = payload["tables"]["semantic_memories"]
        assert len(rows) == 1
        assert "id" not in rows[0]

    def test_merge_dedup_idempotent(self, mem_db, tmp_path):
        dst = tmp_path / "dst.db"
        GBrainBridge(dst)
        _insert(mem_db, "semantic_memories", theme="tema", content="lekcija", kind="principle")
        payload = memory_sync.export_memory(mem_db)
        assert memory_sync.merge_memory(payload, dst)["semantic_memories"] == 1
        assert memory_sync.merge_memory(payload, dst)["semantic_memories"] == 0

    def test_merge_semantic_iste_theme_project_ne_pade(self, mem_db, tmp_path):
        """Regresija: produkcijska DB ima UNIQUE index (theme, project) — merge
        dveh vrstic z istim (theme, project) NE sme pasti na constraint (prej
        "UNIQUE constraint failed: semantic_memories.theme, project")."""
        dst = tmp_path / "dst.db"
        GBrainBridge(dst)
        # Simuliraj produkcijsko DB: UNIQUE index, ki ga svež GBrainBridge ne ustvari.
        with sqlite3.connect(dst) as c:
            memory_sync._ensure_schema(c)
            c.execute("CREATE UNIQUE INDEX idx_semantic_theme ON semantic_memories (theme, project)")
        # Dve vrstici: ista (theme, project), različen content.
        _insert(mem_db, "semantic_memories", theme="tema", project="p1", content="v1", kind="principle")
        _insert(mem_db, "semantic_memories", theme="tema", project="p1", content="v2", kind="principle")
        payload = memory_sync.export_memory(mem_db)
        stats = memory_sync.merge_memory(payload, dst)   # prej: UNIQUE constraint failed
        with sqlite3.connect(dst) as c:
            n = c.execute("SELECT COUNT(*) FROM semantic_memories").fetchone()[0]
        assert n == 1
        assert stats["semantic_memories"] == 1

    def test_merge_run_reviews_dedup(self, mem_db, tmp_path):
        dst = tmp_path / "dst.db"
        GBrainBridge(dst)
        _insert(mem_db, "run_reviews", project="p", directive="d", outcome="ok",
                root_cause="rc", lesson="l")
        payload = memory_sync.export_memory(mem_db)
        assert memory_sync.merge_memory(payload, dst)["run_reviews"] == 1
        assert memory_sync.merge_memory(payload, dst)["run_reviews"] == 0

    def test_agent_nodes_nov_in_posodobljen(self, mem_db, tmp_path):
        dst = tmp_path / "dst.db"
        GBrainBridge(dst)
        _insert(mem_db, "agent_memory_nodes", key="k1", value="v1", tags="")
        payload = memory_sync.export_memory(mem_db)
        assert memory_sync.merge_memory(payload, dst)["agent_memory_nodes"] == 1
        # idempotentno — isti payload ne šteje znova
        assert memory_sync.merge_memory(payload, dst)["agent_memory_nodes"] == 0
        # posodobljena vrednost za isti key → propagira naprej
        _insert(mem_db, "agent_memory_nodes", key="k2", value="v2b", tags="")
        with sqlite3.connect(mem_db) as c:
            c.execute("UPDATE agent_memory_nodes SET value=? WHERE key=?", ("v1b", "k1"))
        payload2 = memory_sync.export_memory(mem_db)
        stats = memory_sync.merge_memory(payload2, dst)
        assert stats["agent_memory_nodes"] == 2   # k1 posodobljen + k2 nov
        with sqlite3.connect(dst) as c:
            assert c.execute("SELECT value FROM agent_memory_nodes WHERE key='k1'").fetchone()[0] == "v1b"

    def test_roundtrip_dva_stroja(self, mem_db, tmp_path):
        dst = tmp_path / "dst.db"
        GBrainBridge(dst)
        _insert(mem_db, "semantic_memories", theme="a", content="x", kind="principle")
        _insert(mem_db, "blacklist_patterns", project="p", error_pattern="e1", mitigation="m")
        stats = memory_sync.merge_memory(memory_sync.export_memory(mem_db), dst)
        assert stats["semantic_memories"] == 1
        assert stats["blacklist_patterns"] == 1
        # nazaj (master ← worker): worker nič novega ne pošlje → 0 povsod
        back = memory_sync.merge_memory(memory_sync.export_memory(dst), mem_db)
        assert all(v == 0 for v in back.values())


class TestFleetMemoryEndpoints:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setattr(memory_sync, "DEFAULT_DB", tmp_path / "mem.db")
        monkeypatch.setattr(audit, "AUDIT_FILE", tmp_path / "audit.jsonl")
        GBrainBridge(memory_sync.DEFAULT_DB)
        return TestClient(fleet.create_app(token="test-token"))

    def test_get_memory(self, client):
        with sqlite3.connect(memory_sync.DEFAULT_DB) as c:
            memory_sync._ensure_schema(c)
            c.execute("INSERT INTO semantic_memories (theme, content, kind) VALUES (?,?,?)",
                      ("t", "c", "principle"))
        r = client.get("/fleet/memory", headers={"Authorization": "Bearer test-token"})
        assert r.status_code == 200
        assert len(r.json()["tables"]["semantic_memories"]) == 1

    def test_post_memory_merge(self, client):
        payload = {"tables": {"semantic_memories": [
            {"theme": "x", "content": "y", "kind": "principle"}]}}
        r = client.post("/fleet/memory", json=payload,
                        headers={"Authorization": "Bearer test-token"})
        assert r.status_code == 200
        assert r.json()["semantic_memories"] == 1
        r2 = client.post("/fleet/memory", json=payload,
                         headers={"Authorization": "Bearer test-token"})
        assert r2.json()["semantic_memories"] == 0   # idempotentno

    def test_memory_zahteva_auth(self, client):
        assert client.get("/fleet/memory").status_code == 401
        assert client.post("/fleet/memory", json={}).status_code == 401

    def test_post_memory_pise_audit_delta(self, client, tmp_path):
        """Novi lekciji ob push-u → audit fleet-memory z delto."""
        payload = {"tables": {"semantic_memories": [
            {"theme": "t-audit", "project": "p", "content": "x", "kind": "principle"}]}}
        r = client.post("/fleet/memory", json=payload,
                        headers={"Authorization": "Bearer test-token"})
        assert r.json()["semantic_memories"] == 1
        txt = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
        assert "fleet-memory" in txt
        assert "+1" in txt


class TestRestorePending:
    def test_restore_importa_pending_skips_obstojecih(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agenda, "AGENDA_FILE", tmp_path / "agenda.json")
        agenda.add("že obstaja", target="postojeci")
        backup = [
            {"id": "a1", "goal": "že obstaja", "target": "postojeci", "status": "pending"},  # skip
            {"id": "a2", "goal": "nova naloga", "target": "novi", "status": "pending"},       # uvoz
            {"id": "a3", "goal": "running", "target": "tec", "status": "running"},            # skip
        ]
        n = agenda.restore_pending(backup)
        assert n == 1
        targets = {i.get("target") for i in agenda.all_()}
        assert "novi" in targets
        assert "tec" not in targets
