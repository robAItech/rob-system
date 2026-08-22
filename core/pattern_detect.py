"""core/pattern_detect.py — P5: prečni vzorci neuspehov čez naloge.

Agregira `run_reviews` po `root_cause` (samo failed) in najde vzorce, ki se
ponavljajo čez ≥2 RAZLIČNA projekta z ≥N skupaj. Vhod v `strategy_reflect`
(P3 — P3 osredotoči predlog načel) in v `learning_dashboard` (P7). Brez LLM.

Uporaba:
  python -m core.pattern_detect --patterns
  python -m core.pattern_detect --patterns --json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.run_review import NEXT_STEP

# P5 — priporočilo za vsak vzrok (izpeljano iz NEXT_STEP — en vir resnice).
RECOMMENDATIONS: Dict[str, str] = {c: v["hint"] for c, v in NEXT_STEP.items()}


class PatternDetector:
    """Iz run_reviews najde prečne vzorce neuspehov (čez projekte)."""

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

    def detect_cross_task_patterns(self, min_projects: int = 2, min_total: int = 3) -> List[Dict[str, Any]]:
        """Prečni vzorci: ista root_cause v ≥min_projects projektih z ≥min_total skupaj."""
        with self._get_connection() as conn:
            try:
                rows = conn.execute(
                    "SELECT root_cause AS cause, COUNT(DISTINCT project) AS projects, "
                    "COUNT(*) AS total FROM run_reviews "
                    "WHERE outcome = 'failed' AND root_cause != 'correct' "
                    "GROUP BY root_cause"
                ).fetchall()
                total_failed = conn.execute(
                    "SELECT COUNT(*) AS n FROM run_reviews WHERE outcome = 'failed'"
                ).fetchone()["n"] or 0
            except sqlite3.OperationalError:
                return []
        patterns = []
        for r in rows:
            cause, projects, total = r["cause"], r["projects"], r["total"]
            if projects >= min_projects and total >= min_total:
                patterns.append({
                    "cause": cause,
                    "projects": projects,
                    "total": total,
                    "share": round(total / total_failed, 4) if total_failed else 0.0,
                    "recommendation": RECOMMENDATIONS.get(cause, ""),
                })
        patterns.sort(key=lambda p: (-p["total"], p["cause"]))
        return patterns

    @staticmethod
    def dominant_pattern(patterns: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Prvi (največji) vzorec ali None."""
        return patterns[0] if patterns else None


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m core.pattern_detect",
                                description="P5 — prečni vzorci neuspehov čez naloge.")
    p.add_argument("--patterns", action="store_true", help="prikaži prečne vzorce")
    p.add_argument("--json", action="store_true", help="izhod kot JSON")
    p.add_argument("--min-projects", type=int, default=2, help="min. različnih projektov")
    p.add_argument("--min-total", type=int, default=3, help="min. skupnih pojavitev")
    args = p.parse_args(argv)

    if args.patterns:
        patterns = PatternDetector().detect_cross_task_patterns(
            min_projects=args.min_projects, min_total=args.min_total)
        if args.json:
            print(json.dumps(patterns, ensure_ascii=False, indent=2))
        elif not patterns:
            print("(ni prečnih vzorcev)")
        else:
            for pa in patterns:
                print(f"[{pa['cause']}] {pa['total']}× v {pa['projects']} projektih "
                      f"({pa['share']:.0%}) — {pa['recommendation']}")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
