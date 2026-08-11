import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, List

class GBrainBridge:
    def __init__(self, db_path: Path = Path(".rob_ai/memory.db")):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
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
