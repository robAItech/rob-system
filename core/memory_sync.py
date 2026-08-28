"""core/memory_sync.py — P9 faza 4: deljen spomin med stroji flote.

Spomin živi v `.rob_ai/memory.db` (SQLite: GBRAIN + semantic tabele). Za
delitev med stroji se "učne" tabele izvozijo v JSON (brez lokalnih autoincrement
id-jev) in na drugem stroju združijo z dedupom po STABILNI identiteti (ki je
enaka čez stroje).

Smer (fleet):
- worker PRED nalogo potegne masterjev izvoz → ima fresh lekcije,
- worker PO nalogi pošlje svoje nove lekcije nazaj masterju (agregacija),
- `rob fleet backup` izvoz + agendo zapiše v git (odpornost — master ni slepa
  ulica), `rob fleet restore` jih združi nazaj.

Dedup identitete (brez lokalnega id-ja):
- semantic_memories : (theme, content)
- run_reviews       : SHA256(directive|outcome|root_cause|lesson|next_step)
- blacklist_patterns: (project, error_pattern)
- agent_memory_nodes: key (UNIQUE v shemi)

Pisanje gre skozi `core.gbrain_bridge.DB_WRITE_LOCK` (isti RLock kot ostali
pisači memory.db) + WAL, da ni `database is locked`.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Optional

from core.gbrain_bridge import DB_WRITE_LOCK

LEARNING_TABLES = (
    "semantic_memories",
    "run_reviews",
    "blacklist_patterns",
    "agent_memory_nodes",
)

DEFAULT_DB = Path(".rob_ai/memory.db")


def _connect(db_path: Path) -> sqlite3.Connection:
    """Povezava z WAL + kratek retry ob `database is locked` (kot gbrain)."""
    last_err: Optional[Exception] = None
    for _ in range(3):
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            return conn
        except sqlite3.OperationalError as e:
            last_err = e
            time.sleep(0.3)
    conn = sqlite3.connect(db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _resolve(db_path) -> Path:
    p = Path(db_path) if db_path else DEFAULT_DB
    return p if p.is_absolute() else Path(__file__).resolve().parent.parent / p


def _row_identity(table: str, row: dict) -> tuple:
    if table == "semantic_memories":
        return ("sm", str(row.get("theme", "")), str(row.get("content", "")))
    if table == "run_reviews":
        h = hashlib.sha256("|".join(str(row.get(k, "")) for k in
                            ("directive", "outcome", "root_cause", "lesson", "next_step"))
                           .encode("utf-8")).hexdigest()
        return ("rr", h)
    if table == "blacklist_patterns":
        return ("bp", str(row.get("project", "")), str(row.get("error_pattern", "")))
    if table == "agent_memory_nodes":
        return ("am", str(row.get("key", "")))
    return ()


def _valid_columns(conn: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


# Sheme učnih tabel — memory_sync je samozadosten (dela tudi na sveži DB,
# kjer semantic_memories/run_reviews/agent_memory_nodes še niso nastale).
_LEARNING_SCHEMAS = {
    "semantic_memories": """
        CREATE TABLE IF NOT EXISTS semantic_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            theme TEXT NOT NULL,
            content TEXT NOT NULL,
            project TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'principle',
            confidence REAL NOT NULL DEFAULT 0.5,
            hits INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            embedding TEXT
        )""",
    "run_reviews": """
        CREATE TABLE IF NOT EXISTS run_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            directive TEXT NOT NULL,
            outcome TEXT NOT NULL,
            root_cause TEXT NOT NULL,
            lesson TEXT,
            llm_calls INTEGER NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            goal TEXT, plan_summary TEXT, task_type TEXT,
            what_worked TEXT, what_failed TEXT, next_step TEXT
        )""",
    "blacklist_patterns": """
        CREATE TABLE IF NOT EXISTS blacklist_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            error_pattern TEXT NOT NULL,
            mitigation TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
    "agent_memory_nodes": """
        CREATE TABLE IF NOT EXISTS agent_memory_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            tags TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""",
}


def _ensure_schema(conn: sqlite3.Connection) -> None:
    for table, sql in _LEARNING_SCHEMAS.items():
        conn.execute(sql)


def export_memory(db_path=None) -> dict:
    """Izvozi učne tabele v {tables: {table: [rows]}}. Brez lokalnih id-jev."""
    db = _resolve(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    out: dict = {}
    with _connect(db) as conn:
        _ensure_schema(conn)
        for table in LEARNING_TABLES:
            rows = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
            for r in rows:
                r.pop("id", None)
            out[table] = rows
    return {"tables": out, "exported_at": int(time.time())}


def merge_memory(payload: dict, db_path=None) -> dict:
    """Združi izvoz (`export_memory` payload) v lokalni memory.db — dedup po
    identiteti. Vrne {table: added}. Idempotentno: ponovljen izvoz doda 0."""
    db = _resolve(db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    incoming = (payload or {}).get("tables", {})
    added: dict = {}
    with DB_WRITE_LOCK:
        with _connect(db) as conn:
            _ensure_schema(conn)
            for table in LEARNING_TABLES:
                rows = incoming.get(table) or []
                if not rows:
                    continue
                cols = _valid_columns(conn, table)
                existing = {_row_identity(table, dict(r))
                            for r in conn.execute(f"SELECT * FROM {table}")}
                n = 0
                for row in rows:
                    if table == "agent_memory_nodes":
                        # key je UNIQUE → propagiraj tudi POSODOBLJENO vrednost
                        # (ne le nove ključe), a ostani idempotenten: isto stanje
                        # ob ponovljenem izvozu ne šteje kot novo.
                        key = str(row.get("key", ""))
                        cur = conn.execute(
                            "SELECT value FROM agent_memory_nodes WHERE key=?", (key,)).fetchone()
                        if cur is not None and cur[0] == row.get("value", ""):
                            continue
                        conn.execute(
                            "INSERT OR REPLACE INTO agent_memory_nodes (key, value, tags, updated_at) "
                            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                            (key, row.get("value", ""), row.get("tags", "")))
                        n += 1
                        continue
                    identity = _row_identity(table, row)
                    if identity in existing:
                        continue
                    insert_cols = [c for c in cols if c != "id" and c in row]
                    if not insert_cols:
                        continue
                    ph = ",".join("?" * len(insert_cols))
                    conn.execute(
                        f"INSERT INTO {table} ({','.join(insert_cols)}) VALUES ({ph})",
                        [row.get(c) for c in insert_cols])
                    existing.add(identity)
                    n += 1
                added[table] = n
    return added


def count_memory(db_path=None) -> dict:
    """Število vrstic po učnih tabelah (za preglede/status)."""
    db = _resolve(db_path)
    out: dict = {}
    with _connect(db) as conn:
        for table in LEARNING_TABLES:
            out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return out
