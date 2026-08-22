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

# P4 — uteži preference (w_success, w_learn). VSOTA = 1.0.
_PREFER_WEIGHTS = {
    "success": (0.7, 0.3),
    "learn":   (0.3, 0.7),
    "balance": (0.5, 0.5),
}
# P4 — prečna širina lekcije glede na akcijo (kako daleč se lekcija prenese).
_TRANSFER = {"build": 0.3, "tune": 0.8, "consolidate": 0.6, "improve": 0.8}
# P4 — uteži znotraj learning_value. VSOTA = 1.0.
_LV_W = {"novelty": 0.4, "weakness": 0.4, "transfer": 0.2}
# P4 — vzroki s širokim prenosom lekcije (sistemski vzorci).
_BROAD_CAUSES = {"recurring_error", "test_gap", "spec_mismatch"}


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
            "dominant_pattern": self._dominant_pattern(),   # P5
        }

    def _dominant_pattern(self) -> Optional[Dict[str, Any]]:
        """P5 — največji prečni vzorec neuspehov (ali None)."""
        try:
            from core.pattern_detect import PatternDetector
            det = PatternDetector(self.db_path)
            return det.dominant_pattern(det.detect_cross_task_patterns())
        except Exception:
            return None

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
    #  P4 — učna vrednost + napoved + score (brez LLM, deterministično)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _weights(prefer: str) -> Tuple[float, float]:
        return _PREFER_WEIGHTS.get(prefer, _PREFER_WEIGHTS["balance"])

    def _learning_value(self, fail_rate: float = 0.0, cause: str = "", action: str = "build",
                        prior_attempts: int = 0) -> float:
        """Deterministična učna vrednost (0..1): novost + šibkost + prenos."""
        novelty = 1.0 / (1.0 + max(0, int(prior_attempts)))
        weakness = max(0.0, min(1.0, float(fail_rate)))
        transfer = _TRANSFER.get(action, 0.3)
        if cause in _BROAD_CAUSES:
            transfer = min(1.0, transfer + 0.1)
        raw = (_LV_W["novelty"] * novelty + _LV_W["weakness"] * weakness
               + _LV_W["transfer"] * transfer)
        return round(min(1.0, raw), 3)

    def _predict(self, goal: str, project: Optional[str] = None, wm=None) -> float:
        """Napovedana verjetnost uspeha (WorldModel.predict); fallback 0.5."""
        try:
            from core.world_model import WorldModel
            wm = wm or WorldModel(self.db_path)
            return float(wm.predict(goal, project).get("success_prob", 0.5))
        except Exception:
            return 0.5

    def _score(self, predicted_success: float, learning_value: float,
               priority: float, prefer: str) -> float:
        """score = (w_success*pred + w_learn*lv) * priority, v [0,1]."""
        w_success, w_learn = self._weights(prefer)
        composite = w_success * float(predicted_success) + w_learn * float(learning_value)
        return round(composite * float(priority), 4)

    def _prior_action_attempts(self, action: str) -> int:
        """Število preteklih poskusov te akcije (run_reviews.task_type, P1)."""
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM run_reviews WHERE task_type = ?", (action,)
                ).fetchone()
                return int(row["n"]) if row else 0
        except sqlite3.OperationalError:
            return 0  # stara baza brez stolpca → 0, tolerantno

    # ------------------------------------------------------------------ #
    #  Predlog nalog
    # ------------------------------------------------------------------ #
    def propose(self, limit: int = 5, prefer: str = "balance") -> List[Dict[str, Any]]:
        """Iz šibkih točk zgradi prioritiziran seznam nalog (P4: score).

        Vsak goal dobi `predicted_success` (WorldModel), `learning_value`
        (novost + šibkost + prenos) in `score`; sort po score desc.
        """
        a = self.analyze()
        goals: List[Dict[str, Any]] = []
        from core.world_model import WorldModel
        wm = WorldModel(self.db_path)

        # Šibki projekti → build/fix (potrebna človeška potrditev).
        for wp in a["weak_projects"]:
            goal_text = f"Zmanjšaj neuspehe v projektu {wp['project']}"
            pred = self._predict(goal_text, wp["project"], wm)
            lv = self._learning_value(fail_rate=wp["fail_rate"], action="build",
                                      prior_attempts=wp["total"])
            goals.append({
                "goal": goal_text,
                "reason": f"{wp['failed']}/{wp['total']} neuspehov ({wp['fail_rate']:.0%})",
                "action": "build",
                "priority": wp["fail_rate"],
                "project": wp["project"],
                "predicted_success": pred,
                "learning_value": lv,
                "score": self._score(pred, lv, wp["fail_rate"], prefer),
            })

        # Ponavljajoča se napaka → uglaševanje heal zanke (varno, reverzibilno).
        n_recurring = a["causes"].get("recurring_error", 0)
        if n_recurring >= 2:
            goal_text = "Uglasi heal zanko (več poskusov / potrpežljivost)"
            prior_tune = self._prior_action_attempts("tune")
            pred = self._predict(goal_text, None, wm)
            lv = self._learning_value(cause="recurring_error", action="tune",
                                      prior_attempts=prior_tune)
            goals.append({
                "goal": goal_text,
                "reason": f"{n_recurring}× ponavljajoča se napaka",
                "action": "tune",
                "priority": 0.5,
                "project": None,
                "predicted_success": pred,
                "learning_value": lv,
                "score": self._score(pred, lv, 0.5, prefer),
            })

        # Veliko znanih pasti → konsolidacija spomina (varno).
        prior_cons = self._prior_action_attempts("consolidate")
        wp_by_project = {wp["project"]: wp for wp in a["weak_projects"]}
        for project, n in a["pitfalls"].items():
            if n >= 3:
                goal_text = f"Naslovi {n} znanih pasti v projektu {project}"
                fail_rate = wp_by_project.get(project, {}).get("fail_rate", 0.0)
                pred = self._predict(goal_text, project, wm)
                lv = self._learning_value(fail_rate=fail_rate, action="consolidate",
                                          prior_attempts=prior_cons)
                goals.append({
                    "goal": goal_text,
                    "reason": f"{n} znanih pasti",
                    "action": "consolidate",
                    "priority": 0.4,
                    "project": project,
                    "predicted_success": pred,
                    "learning_value": lv,
                    "score": self._score(pred, lv, 0.4, prefer),
                })

        goals.sort(key=lambda g: (g["score"], g["priority"], g["goal"]), reverse=True)
        return goals[:limit]

    # ------------------------------------------------------------------ #
    #  Cikel
    # ------------------------------------------------------------------ #
    def run_cycle(self, dry_run: bool = True, limit: int = 3, prefer: str = "balance") -> Dict[str, Any]:
        """Predlaga naloge; če ne dry_run, izvede NAJVARNEJŠI korak (po score)."""
        goals = self.propose(limit, prefer)
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
    p.add_argument("--prefer", choices=["success", "learn", "balance"], default="balance",
                   help="utež pri izbiri naslednje naloge (uspeh / učenje / ravnovesje)")
    args = p.parse_args(argv)

    gp = GoalProposer()
    if args.propose:
        for i, g in enumerate(gp.propose(prefer=args.prefer), 1):
            print(f"{i}. [{g['action']:10}] {g['goal']}  "
                  f"(score={g['score']:.3f} · uspeh={g['predicted_success']:.2f} · "
                  f"učenje={g['learning_value']:.2f})  {g['reason']}")
    elif args.run:
        print(json.dumps(gp.run_cycle(dry_run=False, prefer=args.prefer),
                         ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
