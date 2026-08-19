"""core/tuning.py — Zanka 3 (globlje): samorazvojni PARAMETRI orkestracije.

Medtem ko ``prompt_registry`` verzionira PROMPTE (instructional layer), ta modul
verzionira NUMERIČNE PARAMETRE, ki krmilijo orkestracijo — npr. ``max_attempts``
(koliko heal poskusov) in ``repeat_abort_after`` (kdaj zgodaj prekiniti).

LoopX jih bere od tu (padec nazaj na privzete vrednosti), ``SelfImprover`` pa
jih lahko sam uglasi na podlagi nedavnih recenzij/neuspehov. To je pravi
"RSI nase" na nivoju KODE: sistem spreminja lastne konvergenčne pragove.

VARNOST: vsak parameter ima MEJE (bounds) — vrednost izven mej se zavrne.
Vsaka sprememba je verzionirana + reverzibilna (rollback), kot pri promptih.

Uporaba:
  python core/tuning.py --all       # aktivni parametri
  python core/tuning.py --stats
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

# Privzete vrednosti (če v registru ni aktivne verzije).
DEFAULT_PARAMS: Dict[str, float] = {
    "max_attempts": 5,
    "repeat_abort_after": 3,
}

# Meje (guard): veljavni razponi. Vrednost izven mej se zavrne ob vpisu.
BOUNDS: Dict[str, tuple] = {
    "max_attempts": (1, 10),
    "repeat_abort_after": (1, 10),
}


class Tuning:
    """Verzionirani numerični parametri orkestracije z mejami in rollbackom."""

    def __init__(self, db_path: Path | str = Path(".rob_ai/memory.db")):
        if not Path(db_path).is_absolute():
            self.db_path = PROJECT_ROOT / db_path
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

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
                CREATE TABLE IF NOT EXISTS tuning_values (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    value REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'proposed',
                    note TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tuning_values_name
                ON tuning_values (name, version);
            """)
            conn.commit()

    # ------------------------------------------------------------------ #
    #  Branje / pisanje
    # ------------------------------------------------------------------ #
    def get(self, name: str, default: Optional[float] = None) -> float:
        """Vrne aktivno vrednost parametra, sicer `default` (ali privzeto)."""
        fallback = default if default is not None else DEFAULT_PARAMS.get(name)
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM tuning_values WHERE name = ? AND status = 'active' "
                "ORDER BY version DESC LIMIT 1",
                (name,),
            ).fetchone()
        return float(row["value"]) if row else float(fallback) if fallback is not None else 0.0

    def set(self, name: str, value: float, note: str = "") -> int:
        """Vpiše novo (predlagano) vrednost; preveri meje. Vrne id verzije."""
        if name in BOUNDS:
            lo, hi = BOUNDS[name]
            if not (lo <= value <= hi):
                raise ValueError(f"{name}={value} izven mej {BOUNDS[name]}")
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS v FROM tuning_values WHERE name = ?",
                (name,),
            ).fetchone()
            version = int(row["v"]) + 1
            cur = conn.execute(
                "INSERT INTO tuning_values (name, version, value, status, note) "
                "VALUES (?, ?, ?, 'proposed', ?)",
                (name, version, value, note),
            )
            conn.commit()
            return int(cur.lastrowid)

    def promote(self, name: str, version_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE tuning_values SET status = 'superseded' WHERE name = ? AND status = 'active'",
                (name,),
            )
            conn.execute("UPDATE tuning_values SET status = 'active' WHERE id = ?", (version_id,))
            conn.commit()
        self._audit("tuning-promote", name, f"version_id={version_id}")

    def rollback(self, name: str) -> Optional[int]:
        with self._get_connection() as conn:
            active = conn.execute(
                "SELECT id, version FROM tuning_values WHERE name = ? AND status = 'active' "
                "ORDER BY version DESC LIMIT 1",
                (name,),
            ).fetchone()
            if not active:
                return None
            prev = conn.execute(
                "SELECT id FROM tuning_values WHERE name = ? AND status = 'superseded' "
                "AND version < ? ORDER BY version DESC LIMIT 1",
                (name, active["version"]),
            ).fetchone()
            if not prev:
                return None
            conn.execute("UPDATE tuning_values SET status = 'superseded' WHERE id = ?", (active["id"],))
            conn.execute("UPDATE tuning_values SET status = 'active' WHERE id = ?", (prev["id"],))
            conn.commit()
            self._audit("tuning-rollback", name, f"from={active['id']} to={prev['id']}")
            return int(prev["id"])

    def all(self) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for name in DEFAULT_PARAMS:
            out[name] = self.get(name)
        return out

    def history(self, name: str, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM tuning_values WHERE name = ? ORDER BY version DESC LIMIT ?",
                (name, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM tuning_values").fetchone()["n"]
            by_status = {r["status"]: r["n"] for r in conn.execute(
                "SELECT status, COUNT(*) AS n FROM tuning_values GROUP BY status"
            ).fetchall()}
        return {"versions": total, "by_status": by_status, "active": self.all()}

    @staticmethod
    def _audit(event: str, name: str, detail: str) -> None:
        try:
            from core.audit import record
            record(event=event, project=name, status="ok", detail=detail)
        except Exception:
            pass


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="tuning", description="Zanka 3 — samorazvojni parametri orkestracije.")
    p.add_argument("--all", action="store_true", help="aktivni parametri")
    p.add_argument("--stats", action="store_true", help="statistika")
    args = p.parse_args(argv)

    t = Tuning()
    if args.all or args.stats:
        print(json.dumps(t.stats() if args.stats else t.all(), ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
