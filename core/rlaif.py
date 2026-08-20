"""core/rlaif.py — Faza 9 / Zanka 9: RLAIF — učenje preferenc.

Zanke 1–8 zbirajo trajektorije z izidi. Zanka 9 iz njih zgradi PREFERENCE PODATKE
za učenje: pare (chosen, rejected), kjer je chosen boljši (zelen) in rejected
slabši (neuspešen) pristop k istemu projektu/cilju.

To je podatkovni cevovod za fine-tuning (DPO/RLHF). Sam fine-tuning je LOČEN
infrastrukturni korak (GPU + ogrodje) — ta modul pripravi podatke v standardnem
DPO formatu (JSONL), pripravljene za trening.

To je prva zanka, ki se dotakne UTEŽI (ne le promptov/parametrov): podatki, ki
jih izvozi, so tisto, kar omogoči, da se model dejansko nauči preferenc sistema.

Uporaba:
  python core/rlaif.py --stats
  python core/rlaif.py --export rlaif_prefs.jsonl
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class PreferenceCollector:
    """Iz trajektorij izlušči preference pare (chosen, rejected) za fine-tuning."""

    def __init__(self, db_path: Path | str = Path(".rob_ai/memory.db")):
        if not Path(db_path).is_absolute():
            self.db_path = PROJECT_ROOT / db_path
        else:
            self.db_path = Path(db_path)

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

    # ------------------------------------------------------------------ #
    #  Zbiranje preference parov
    # ------------------------------------------------------------------ #
    def collect_pairs(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Izlušči (chosen, rejected) pare: zelen vs neuspešen pristop istega projekta."""
        with self._get_connection() as conn:
            try:
                rows = conn.execute(
                    "SELECT project, prompt, status FROM task_history ORDER BY task_id"
                ).fetchall()
            except sqlite3.OperationalError:
                return []

        by_project: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: {"green": [], "failed": []})
        for r in rows:
            status = (r["status"] or "").upper()
            if status == "VERIFIED GREEN":
                by_project[r["project"]]["green"].append(r["prompt"])
            elif "FAIL" in status:
                by_project[r["project"]]["failed"].append(r["prompt"])

        pairs: List[Dict[str, str]] = []
        for project, d in by_project.items():
            if d["green"] and d["failed"]:
                pairs.append({
                    "prompt": project,
                    "chosen": d["green"][0],
                    "rejected": d["failed"][0],
                })
        if limit:
            pairs = pairs[:limit]
        return pairs

    def export(self, path: str, limit: Optional[int] = None) -> int:
        """Zapiše preference pare v JSONL (DPO format). Vrne število zapisanih."""
        pairs = self.collect_pairs(limit)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for p in pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        return len(pairs)

    def stats(self) -> Dict[str, Any]:
        pairs = self.collect_pairs()
        with self._get_connection() as conn:
            green = failed = 0
            try:
                green = conn.execute(
                    "SELECT COUNT(*) AS n FROM task_history WHERE status = 'VERIFIED GREEN'"
                ).fetchone()["n"]
                failed = conn.execute(
                    "SELECT COUNT(*) AS n FROM task_history WHERE status LIKE '%FAIL%'"
                ).fetchone()["n"]
            except sqlite3.OperationalError:
                pass
        return {"pairs": len(pairs), "green": green, "failed": failed}


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="rlaif", description="Zanka 9 — učenje preferenc (RLAIF).")
    p.add_argument("--stats", action="store_true", help="koliko preference parov je na voljo")
    p.add_argument("--export", metavar="PATH", help="izvozi JSONL (DPO format) za fine-tuning")
    args = p.parse_args(argv)

    pc = PreferenceCollector()
    if args.stats:
        print(json.dumps(pc.stats(), ensure_ascii=False, indent=2))
    elif args.export:
        n = pc.export(args.export)
        print(f"Izvoženih {n} preference parov → {args.export}")
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
