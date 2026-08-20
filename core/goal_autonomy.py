"""core/goal_autonomy.py — Faza 10 / Zanka 10: avtonomija ciljev.

Zanke 1–9 zbirajo signal o tem, kje je sistem ŠIBEK (neuspehi, ponavljajoče se
napake, znane pasti, metrike). Zanka 10 ta signal prebere in PREDLAGA naslednjo
nalogo: sistem sam vodi svoj dnevni red, človek samo potrdi.

Varni, REVERZIBILNI koraki se lahko izvedejo samodejno:
  - ``tune``       — uglaševanje parametrov (Zanka 3, reverzibilno),
  - ``consolidate``— spominska konsolidacija (Zanka 1, varna),
  - ``improve``    — samorazvoj prompta (Zanka 3, gated + rollback).
Koda-zahtevni koraki (``build``/``fix``) se samo PREDLAGAJO (človek potrdi).

To zapre vseh deset zank v SAMOSTOJEN cikel.

Uporaba:
  python core/goal_autonomy.py --propose
  python core/goal_autonomy.py --run          # predlagaj + izvedi najvarnejši korak
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class GoalProposer:
    """Iz lastnih šibkih točk predlaga naslednjo nalogo (avtonomija ciljev)."""

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
    #  Analiza šibkih točk
    # ------------------------------------------------------------------ #
    def analyze(self) -> Dict[str, Any]:
        return {
            "weak_projects": self._weak_projects(),
            "causes": self._cause_counts(),
            "pitfalls": self._pitfall_counts(),
        }

    def _weak_projects(self, min_total: int = 3, min_fail_rate: float = 0.4) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            try:
                rows = conn.execute(
                    "SELECT project, COUNT(*) AS t, "
                    "SUM(CASE WHEN status LIKE '%FAIL%' THEN 1 ELSE 0 END) AS f "
                    "FROM task_history GROUP BY project"
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        out = []
        for r in rows:
            total, failed = r["t"], r["f"] or 0
            if total >= min_total and failed / total >= min_fail_rate:
                out.append({
                    "project": r["project"],
                    "fail_rate": round(failed / total, 2),
                    "failed": failed,
                    "total": total,
                })
        return out

    def _cause_counts(self) -> Dict[str, int]:
        with self._get_connection() as conn:
            try:
                rows = conn.execute(
                    "SELECT root_cause, COUNT(*) AS n FROM run_reviews GROUP BY root_cause"
                ).fetchall()
            except sqlite3.OperationalError:
                return {}
        return {r["root_cause"]: r["n"] for r in rows}

    def _pitfall_counts(self) -> Dict[str, int]:
        with self._get_connection() as conn:
            try:
                rows = conn.execute(
                    "SELECT project, COUNT(*) AS n FROM blacklist_patterns GROUP BY project"
                ).fetchall()
            except sqlite3.OperationalError:
                return {}
        return {r["project"]: r["n"] for r in rows}

    # ------------------------------------------------------------------ #
    #  Predlog nalog
    # ------------------------------------------------------------------ #
    def propose(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Iz šibkih točk zgradi prioritiziran seznam nalog (goal + reason + action)."""
        a = self.analyze()
        goals: List[Dict[str, Any]] = []

        # Šibki projekti → build/fix (potrebna človeška potrditev).
        for wp in a["weak_projects"]:
            goals.append({
                "goal": f"Zmanjšaj neuspehe v projektu {wp['project']}",
                "reason": f"{wp['failed']}/{wp['total']} neuspehov ({wp['fail_rate']:.0%})",
                "action": "build",
                "priority": wp["fail_rate"],
            })

        # Ponavljajoča se napaka → uglaševanje heal zanke (varno, reverzibilno).
        n_recurring = a["causes"].get("recurring_error", 0)
        if n_recurring >= 2:
            goals.append({
                "goal": "Uglasi heal zanko (več poskusov / potrpežljivost)",
                "reason": f"{n_recurring}× ponavljajoča se napaka",
                "action": "tune",
                "priority": 0.5,
            })

        # Veliko znanih pasti → konsolidacija spomina (varno).
        for project, n in a["pitfalls"].items():
            if n >= 3:
                goals.append({
                    "goal": f"Naslovi {n} znanih pasti v projektu {project}",
                    "reason": f"{n} znanih pasti",
                    "action": "consolidate",
                    "priority": 0.4,
                })

        goals.sort(key=lambda g: g["priority"], reverse=True)
        return goals[:limit]

    # ------------------------------------------------------------------ #
    #  Cikel
    # ------------------------------------------------------------------ #
    def run_cycle(self, dry_run: bool = True, limit: int = 3) -> Dict[str, Any]:
        """Predlaga naloge; če ne dry_run, izvede NAJVARNEJŠI korak."""
        goals = self.propose(limit)
        result: Dict[str, Any] = {"proposed": goals}
        if not dry_run and goals:
            top = goals[0]
            result["dispatched"] = {"goal": top["goal"], "result": self._dispatch(top)}
        return result

    def _dispatch(self, goal: Dict[str, Any]) -> Dict[str, Any]:
        """Izvede varen, reverzibilen korak; build/fix vrne 'preskočeno'."""
        action = goal["action"]
        if action == "tune":
            from core.self_improve import SelfImprover
            return SelfImprover(self.db_path).tune_cycle(dry_run=True)
        if action == "consolidate":
            from core.memory_consolidation import MemoryConsolidator
            return MemoryConsolidator(self.db_path).consolidate()
        if action == "improve":
            from core.self_improve import SelfImprover
            imp = SelfImprover(self.db_path)
            from core.loopx_bridge import RSI_PROMPT_SYSTEM
            current = imp.registry.get_active("rsi_heal_system", RSI_PROMPT_SYSTEM)
            return imp.run_cycle(current, imp.gather_context(), dry_run=True)
        return {"skipped": "potrebna človeška potrditev (sprememba kode)"}


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="goal_autonomy", description="Zanka 10 — avtonomija ciljev.")
    p.add_argument("--propose", action="store_true", help="predlagaj naslednje naloge")
    p.add_argument("--run", action="store_true", help="predlagaj in izvedi najvarnejši korak")
    args = p.parse_args(argv)

    gp = GoalProposer()
    if args.propose:
        for i, g in enumerate(gp.propose(), 1):
            print(f"{i}. [{g['action']:10}] {g['goal']}  ({g['reason']})")
    elif args.run:
        print(json.dumps(gp.run_cycle(dry_run=False), ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
