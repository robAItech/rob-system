import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # repo koren (core/ → koren)

class GBrainBridge:
    def __init__(self, db_path: Path = Path(".rob_ai/memory.db")):
        # P2 — sočasnost: privzeti relativni db_path razreši iz REPO KORENA, ne iz cwd.
        # Na ta način sočasni buildi iz različnih cwd-jev uporabijo ISTI memory.db
        # (prej je bil relativni na cwd → več db ali "database is locked" ob prepletu).
        # Eksplicitni (absolutni) db_path — npr. v tmp-testeh — ostane nespremenjen.
        if not db_path.is_absolute():
            self.db_path = PROJECT_ROOT / db_path
        else:
            self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        # P2 — retry na "database is locked": sočasni pisači se ne zrušijo,
        # ampak počakajo (do 3 poskuse s kratkim spancem).
        last_err: Optional[Exception] = None
        for _ in range(3):
            try:
                conn = sqlite3.connect(self.db_path, timeout=5)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                return conn
            except sqlite3.OperationalError as e:
                last_err = e
                time.sleep(0.3)
        # Zadnji poskus brez WAL (če WAL ni na voljo) — še vedno poveži.
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_history (
                    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    traceback TEXT,
                    verified_code TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blacklist_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    error_pattern TEXT NOT NULL,
                    mitigation TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_memory_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    def record_task(self, project: str, prompt: str, status: str, traceback: str = "", verified_code: str = "") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO task_history (project, prompt, status, traceback, verified_code) VALUES (?, ?, ?, ?, ?)",
                (project, prompt, status, traceback, verified_code)
            )
            conn.commit()
            return cursor.lastrowid

    def add_blacklist_pattern(self, project: str, error_pattern: str, mitigation: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO blacklist_patterns (project, error_pattern, mitigation) VALUES (?, ?, ?)",
                (project, error_pattern, mitigation)
            )
            conn.commit()

    def get_blacklists(self, project: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM blacklist_patterns WHERE project = ?", (project,)).fetchall()
            return [dict(r) for r in rows]

    def store_memory_node(self, key: str, data: Dict[str, Any], tags: List[str]) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agent_memory_nodes (key, value, tags) VALUES (?, ?, ?)",
                (key, json.dumps(data), ",".join(tags))
            )
            conn.commit()