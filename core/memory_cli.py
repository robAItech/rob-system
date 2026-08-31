"""core/memory_cli.py — pregled in reset učnega spomina (rob memory).

Uporaba:
  python core/memory_cli.py          # števila po učnih tabelah
  python core/memory_cli.py --reset  # popoln reset učnih tabel (testno/učno
                                     # stanje — ne dotika se sistemske baze ali
                                     # konfiguracije)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB = PROJECT_ROOT / ".rob_ai" / "memory.db"

# Učne tabele, ki se reset-irajo — vse je pridobljeno znanje iz izvedenih nalog
# (testnih ali realnih). Sistemsko stanje (agenda, daemon heartbeat, ...) ni tu.
LEARNING_TABLES: tuple = (
    "semantic_memories",     # principi/past/procedure (učno znanje)
    "blacklist_patterns",    # vzorci napak + mitigacije
    "agent_memory_nodes",    # ključ-vrednost spomin (visual_qa ipd.)
    "meta_snapshots",        # regression baseline-i (stari, če je zgodovina zbrisana)
    "consolidation_state",   # napredek konsolidacije
    "prompt_versions",       # samorazvoj prompta (RSI)
    "tuning_values",         # uglaševanje parametrov
    "run_reviews",           # pregledi tekov (uspeh/neuspeh → kvaliteta)
    "task_history",          # surove epizode (VERIFIED GREEN/FAILED)
)


def _count_all() -> dict:
    conn = sqlite3.connect(DB)
    out = {}
    for t in LEARNING_TABLES:
        try:
            out[t] = int(conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
        except sqlite3.OperationalError:
            out[t] = -1  # tabela ne obstaja
    conn.close()
    return out


def _show() -> int:
    for table, n in _count_all().items():
        print(f"  {table:<22} {n if n >= 0 else '(ni tabele)'}")
    return 0


def _reset() -> int:
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cleared = 0
    for t in LEARNING_TABLES:
        try:
            cur.execute(f"DELETE FROM {t}")
            cleared += cur.rowcount
        except sqlite3.OperationalError:
            continue
    conn.commit()
    conn.close()
    print(f"Reset učnih tabel: {cleared} vrstic počiščeno.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="rob memory",
                                description="Pregled/reset učnega spomina.")
    p.add_argument("--reset", action="store_true",
                   help="popoln reset učnih tabel (učenje iz nič)")
    args = p.parse_args(argv)

    print("Učni spomin (memory.db):")
    return _reset() if args.reset else _show()


if __name__ == "__main__":
    raise SystemExit(main())
