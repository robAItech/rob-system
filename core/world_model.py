"""core/world_model.py — Faza 7 / Zanka 7: svetovni model (napoved izidov).

Sistem ima trajektorije: ``task_history`` (uspeh/neuspeh po teku),
``run_reviews`` (vzroki, LLM strošek) in ``blacklist_patterns`` (znane pasti).
Zanka 7 se iz njih NAUČI napovedovati izid PRED izvedbo:

  - ``success_prob``     — verjetnost uspeha (projektna → globalna, znižana za pasti),
  - ``expected_llm_calls`` — pričakovan LLM strošek,
  - ``likely_cause``     — najpogostejši vzrok neuspeha.

To je prva zanka, ki sistemu da PREDVIDEVANJE (ne le retrospektivo). Napoved
se uporablja v Zanki 5 (izberi načrt z največjo verjetnostjo uspeha) in Zanki 6
(critic dobi kvantitativno oceno tveganja).

Ni globoko učenje — je statističen model nad lastnimi trajektorijami, kar je
poštena, dosegljiva različica "svetovnega modela" na tej stopnji.

Uporaba:
  python core/world_model.py --predict "zgradi API za avtentikacijo" --project auth
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class WorldModel:
    """Statističen prediktor izidov nad lastnimi trajektorijami."""

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
    #  Statistika iz trajektorij
    # ------------------------------------------------------------------ #
    def _stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total = green = 0
            try:
                total = conn.execute("SELECT COUNT(*) AS n FROM task_history").fetchone()["n"]
                green = conn.execute(
                    "SELECT COUNT(*) AS n FROM task_history WHERE status = 'VERIFIED GREEN'"
                ).fetchone()["n"]
            except sqlite3.OperationalError:
                pass
            avg_llm = 0.0
            by_cause: Dict[str, int] = {}
            try:
                row = conn.execute("SELECT AVG(llm_calls) AS a FROM run_reviews").fetchone()
                avg_llm = float(row["a"]) if row and row["a"] is not None else 0.0
                by_cause = {r["root_cause"]: r["n"] for r in conn.execute(
                    "SELECT root_cause, COUNT(*) AS n FROM run_reviews GROUP BY root_cause"
                ).fetchall()}
            except sqlite3.OperationalError:
                pass
        return {
            "total": total,
            "green": green,
            "success_rate": round(green / total, 4) if total else None,
            "avg_llm_calls": round(avg_llm, 3),
            "by_cause": by_cause,
        }

    def _project_success_rate(self, project: str) -> Optional[float]:
        with self._get_connection() as conn:
            try:
                total = conn.execute(
                    "SELECT COUNT(*) AS n FROM task_history WHERE project = ?", (project,)
                ).fetchone()["n"]
                green = conn.execute(
                    "SELECT COUNT(*) AS n FROM task_history WHERE project = ? AND status = 'VERIFIED GREEN'",
                    (project,),
                ).fetchone()["n"]
            except sqlite3.OperationalError:
                return None
        return round(green / total, 4) if total else None

    def _project_pitfalls(self, project: str) -> int:
        with self._get_connection() as conn:
            try:
                return conn.execute(
                    "SELECT COUNT(*) AS n FROM blacklist_patterns WHERE project = ?", (project,)
                ).fetchone()["n"]
            except sqlite3.OperationalError:
                return 0

    # ------------------------------------------------------------------ #
    #  Napoved
    # ------------------------------------------------------------------ #
    @staticmethod
    def _detect_kind(goal: str) -> str:
        d = (goal or "").lower()

        def has(word: str) -> bool:
            return re.search(rf"\b{re.escape(word)}\b", d) is not None

        if any(has(w) for w in ("html", "dashboard", "spletni", "spletna")) \
                or ".html" in d or "<html" in d or "spletna stran" in d:
            return "html"
        if any(has(w) for w in ("markdown", "predlog", "poročilo", "roadmap")) \
                or ".md" in d or "md datoteko" in d:
            return "markdown"
        return "python"

    def predict(self, goal: str, project: Optional[str] = None) -> Dict[str, Any]:
        """Napove izid za cilj: uspešnost, LLM strošek, verjeten vzrok."""
        stats = self._stats()
        kind = self._detect_kind(goal)
        pitfalls = self._project_pitfalls(project) if project else 0

        # Osnova: projektna uspešnost (če obstaja), sicer globalna, sicer 0.5.
        project_sr = self._project_success_rate(project) if project else None
        base = project_sr if project_sr is not None else (stats["success_rate"] or 0.5)

        # Znane pasti (blacklisti) znižajo verjetnost uspeha.
        success_prob = max(0.05, min(0.95, base - pitfalls * 0.05))

        by_cause = stats["by_cause"]
        likely_cause = max(by_cause, key=by_cause.get) if by_cause else None

        return {
            "kind": kind,
            "success_prob": round(success_prob, 3),
            "expected_llm_calls": stats["avg_llm_calls"],
            "likely_cause": likely_cause,
            "pitfalls": pitfalls,
            "samples": stats["total"],
            "base_rate": round(base, 4) if base is not None else None,
        }

    def predict_batch(self, goals: List[str], project: Optional[str] = None) -> List[Dict[str, Any]]:
        """Napove izid za več kandidatnih ciljev (npr. podcilje iz Zanke 5)."""
        return [self.predict(g, project) for g in goals]

    def best(self, goals: List[str], project: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """Vrne cilj z največjo verjetnostjo uspeha (za izbiro načrta)."""
        preds = self.predict_batch(goals, project)
        if not preds:
            raise ValueError("prazen seznam ciljev")
        idx = max(range(len(preds)), key=lambda i: preds[i]["success_prob"])
        return goals[idx], preds[idx]

    def stats(self) -> Dict[str, Any]:
        return self._stats()


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="world_model", description="Zanka 7 — svetovni model (napoved izidov).")
    p.add_argument("--predict", metavar="GOAL", help="napove izid za cilj")
    p.add_argument("--project", default=None, help="ciljni modul")
    p.add_argument("--stats", action="store_true", help="globalna statistika")
    args = p.parse_args(argv)

    wm = WorldModel()
    if args.predict:
        print(json.dumps(wm.predict(args.predict, args.project), ensure_ascii=False, indent=2))
    elif args.stats:
        print(json.dumps(wm.stats(), ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
