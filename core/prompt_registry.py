"""core/prompt_registry.py — Faza 4d / Zanka 3: verzioniran register promptov.

RSI sistem-prompt (``RSI_PROMPT_SYSTEM`` v ``loopx_bridge``) je danes trdo
kodiran. Ta modul ga preseli v VERZIONIRANO shrambo: sistem lahko predlaga novo
verzijo prompta, jo preveri z regresijsko množico in jo promovira — ali vrne
nazaj (rollback).

Vsaka sprememba je zapisana (auditabilna), vsaka promocija ima rollback na
prejšnjo aktivno verzijo. To je "commit kot event" na Python strani: sprememba
orchestracijskega prompta je vedno reverzibilna in sledljiva.

Uporaba:
  python core/prompt_registry.py --history rsi_heal_system
  python core/prompt_registry.py --stats
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Statusi verzij prompta.
STATUSES = ("proposed", "active", "superseded", "rejected")


class PromptRegistry:
    """Verzioniran register promptov z rollbackom.

    Živi v isti bazi kot GBRAIN (``.rob_ai/memory.db``); lasti tabelo
    ``prompt_versions``. Aktivna verzija določenega prompta se bere prek
    ``get_active``; ``rollback`` vrne sistem na prejšnjo aktivno verzijo.
    """

    def __init__(self, db_path: Path | str = Path(".rob_ai/memory.db")):
        if not Path(db_path).is_absolute():
            self.db_path = PROJECT_ROOT / db_path
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------ #
    #  Povezava + shema
    # ------------------------------------------------------------------ #
    def _get_connection(self) -> sqlite3.Connection:
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
        conn = sqlite3.connect(self.db_path, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    note TEXT,
                    tests_passed INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prompt_versions_name
                ON prompt_versions (name, version);
            """)
            conn.commit()

    # ------------------------------------------------------------------ #
    #  Branje / pisanje
    # ------------------------------------------------------------------ #
    def get_active(self, name: str, default: str = "") -> str:
        """Vrne vsebino aktivne verzije prompta, sicer `default`."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT content FROM prompt_versions WHERE name = ? AND status = 'active' "
                "ORDER BY version DESC LIMIT 1",
                (name,),
            ).fetchone()
        return str(row["content"]) if row else default

    def propose(self, name: str, content: str, note: str = "") -> int:
        """Zabeleži nov (še neaktivni) predlog. Vrne id verzije."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS v FROM prompt_versions WHERE name = ?",
                (name,),
            ).fetchone()
            version = int(row["v"]) + 1
            cur = conn.execute(
                "INSERT INTO prompt_versions (name, version, content, status, note) "
                "VALUES (?, ?, ?, 'proposed', ?)",
                (name, version, content, note),
            )
            conn.commit()
            return int(cur.lastrowid)

    def mark(self, version_id: int, status: str, tests_passed: Optional[int] = None) -> None:
        if status not in STATUSES:
            raise ValueError(f"neznan status '{status}'")
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE prompt_versions SET status = ?, tests_passed = ? WHERE id = ?",
                (status, tests_passed, version_id),
            )
            conn.commit()

    def promote(self, name: str, version_id: int) -> None:
        """Postavi verzijo za aktivno; vse druge aktivne postanejo superseded."""
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE prompt_versions SET status = 'superseded' WHERE name = ? AND status = 'active'",
                (name,),
            )
            conn.execute(
                "UPDATE prompt_versions SET status = 'active', tests_passed = 1 WHERE id = ?",
                (version_id,),
            )
            conn.commit()
        self._audit("prompt-promote", name, f"version_id={version_id}")

    def rollback(self, name: str) -> Optional[int]:
        """Vrne na prejšnjo aktivno verzijo (superseded). Vrne nov aktivni id.

        Vrne None, če ni prejšnje verzije (nič za rollback).
        """
        with self._get_connection() as conn:
            active = conn.execute(
                "SELECT id, version FROM prompt_versions WHERE name = ? AND status = 'active' "
                "ORDER BY version DESC LIMIT 1",
                (name,),
            ).fetchone()
            if not active:
                return None
            prev = conn.execute(
                "SELECT id FROM prompt_versions WHERE name = ? AND status = 'superseded' "
                "AND version < ? ORDER BY version DESC LIMIT 1",
                (name, active["version"]),
            ).fetchone()
            if not prev:
                return None
            conn.execute("UPDATE prompt_versions SET status = 'superseded' WHERE id = ?", (active["id"],))
            conn.execute("UPDATE prompt_versions SET status = 'active' WHERE id = ?", (prev["id"],))
            conn.commit()
            self._audit("prompt-rollback", name, f"from={active['id']} to={prev['id']}")
            return int(prev["id"])

    def history(self, name: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM prompt_versions WHERE name = ? ORDER BY version DESC LIMIT ?",
                (name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM prompt_versions").fetchone()["n"]
            by_status = {r["status"]: r["n"] for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM prompt_versions GROUP BY status"
            ).fetchall()}
        return {"versions": total, "by_status": by_status}

    @staticmethod
    def _audit(event: str, name: str, detail: str) -> None:
        try:
            from core.audit import record
            record(event=event, project=name, status="ok", detail=detail)
        except Exception:
            pass  # revizija nikoli ne sme blokirati promocije


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="prompt_registry", description="Zanka 3 — verzioniran register promptov.")
    p.add_argument("--history", metavar="NAME", help="zgodovina verzij prompta")
    p.add_argument("--stats", action="store_true", help="statistika registra")
    args = p.parse_args(argv)

    r = PromptRegistry()
    if args.history:
        for row in r.history(args.history):
            print(f"v{row['version']} [{row['status']:10}] (id={row['id']}) {row['note'] or ''}")
    elif args.stats:
        print(json.dumps(r.stats(), ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
