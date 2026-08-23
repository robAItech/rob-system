"""core/meta_eval.py — Faza 4f / Zanka 4: meta-evalvacija samorazvoja.

Zanke 1–3 omogočijo sistemu, da se UČI (1), PRESOJA (2) in IZBOLJŠUJE (3).
Zanka 4 pa MERI, ali izboljšave dejansko pomagajo — in avtomatsko POVRNE tiste,
ki so stvari poslabšale. To zapre meta-zanko: sistem ne le da se izboljšuje,
ampak preverja, da njegove izboljšave delujejo.

Metrike (iz task_history + run_reviews):
  - success_rate = zelenih / vseh tekov
  - avg_llm_calls = povprečno LLM klicev na tek
  - by_cause = porazdelitev neuspehov po vzroku

Cikel:
  1. ``snapshot()`` pred samorazvojno spremembo (baseline),
  2. (sistem se samorazvije — Zanka 3 — in opravi nekaj tekov),
  3. ``check()`` primerja in avtomatsko povrne prompt/parametre ob regresiji.

Uporaba:
  python core/meta_eval.py --metrics
  python core/meta_eval.py --snapshot "pred tune"
  python core/meta_eval.py --check <snapshot_id>
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

# Pragovi regresije (koliko se mora poslabšati, da šteje kot regresija).
REGRESSION_SUCCESS_DROP = 0.05   # uspešnost pade za >5 odstotnih točk
REGRESSION_LLM_RISE = 0.20       # povprečni LLM klici narastejo za >20%

# C3 — verzija metrike: 1 = stara (task_history, onesnažena s test_proj),
# 2 = poštena (run_reviews). Snapshoti različnih verzij so NEprimerljivi →
# compare() jih preskoči (brez lažne regresije/rollbacka).
METRIC_VERSION = 2


class MetaEvaluator:
    """Meri učinek samorazvoja in avtomatsko povrne regresivne spremembe."""

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
                CREATE TABLE IF NOT EXISTS meta_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT,
                    metrics TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    # ------------------------------------------------------------------ #
    #  Metrike
    # ------------------------------------------------------------------ #
    def metrics(self) -> Dict[str, Any]:
        """Poštene metrike iz run_reviews (čista tabela — NIKOLI task_history).

        task_history je onesnažen s `test_proj` vrsticami iz test harnessa (43/56),
        zato se ne uporablja več za uspešnost. run_reviews vsebuje samo prave
        orkestratorske builde (outcome 'green'|'failed').
        """
        with self._get_connection() as conn:
            runs = green = 0
            try:
                runs = conn.execute("SELECT COUNT(*) AS n FROM run_reviews").fetchone()["n"]
                green = conn.execute(
                    "SELECT COUNT(*) AS n FROM run_reviews WHERE outcome = 'green'"
                ).fetchone()["n"]
            except sqlite3.OperationalError:
                runs = green = 0  # run_reviews še ne obstaja

            avg_llm = None
            by_cause: Dict[str, int] = {}
            try:
                row = conn.execute("SELECT AVG(llm_calls) AS a FROM run_reviews").fetchone()
                avg_llm = round(float(row["a"]), 3) if row and row["a"] is not None else 0.0
                by_cause = {r["root_cause"]: r["n"] for r in conn.execute(
                    "SELECT root_cause, COUNT(*) AS n FROM run_reviews GROUP BY root_cause"
                ).fetchall()}
            except sqlite3.OperationalError:
                pass  # run_reviews še ne obstaja

        failed = runs - green
        return {
            "runs": runs,
            "green": green,
            "failed": failed,
            "success_rate": round(green / runs, 4) if runs else 1.0,
            "avg_llm_calls": avg_llm,
            "by_cause": by_cause,
            "metric_version": METRIC_VERSION,
        }

    # ------------------------------------------------------------------ #
    #  Snapshot / primerjava / rollback
    # ------------------------------------------------------------------ #
    def snapshot(self, label: str = "") -> int:
        """Shrani trenutne metrike kot baseline. Vrne id snapshot-a."""
        m = self.metrics()
        with self._get_connection() as conn:
            cur = conn.execute(
                "INSERT INTO meta_snapshots (label, metrics) VALUES (?, ?)",
                (label, json.dumps(m, ensure_ascii=False)),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_snapshot(self, snapshot_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM meta_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["metrics"] = json.loads(d["metrics"])
            return d

    def compare(self, before_id: int) -> Dict[str, Any]:
        """Primerja trenutne metrike s snapshot-om. Vrne {regressed, deltas}. """
        before = self.get_snapshot(before_id)
        if not before:
            return {"regressed": False, "error": f"snapshot {before_id} ne obstaja"}
        after = self.metrics()
        b = before["metrics"]
        # C3 — verzijski gate: stari (task_history, v1) in novi (run_reviews, v2)
        # snapshoti niso primerljivi → NE sproži lažne regresije/rollbacka.
        if int(b.get("metric_version") or 1) != int(after.get("metric_version") or 1):
            return {
                "regressed": False,
                "incomparable": True,
                "reason": "stari snapshoti (task_history) niso primerljivi z novimi (run_reviews)",
                "before": b,
                "after": after,
            }

        success_delta = after["success_rate"] - b["success_rate"]
        llm_before = float(b.get("avg_llm_calls") or 0.0)
        llm_after = float(after.get("avg_llm_calls") or 0.0)
        llm_delta = llm_after - llm_before
        llm_rise_ratio = (llm_delta / llm_before) if llm_before > 0 else 0.0

        regressed = (
            success_delta < -REGRESSION_SUCCESS_DROP
            or llm_rise_ratio > REGRESSION_LLM_RISE
        )
        return {
            "regressed": regressed,
            "success_delta": round(success_delta, 4),
            "llm_delta": round(llm_delta, 3),
            "llm_rise_ratio": round(llm_rise_ratio, 3),
            "before": b,
            "after": after,
        }

    def rollback_improvements(self) -> Dict[str, Any]:
        """Povrne zadnje samorazvojne spremembe (prompt + parametri). Best-effort."""
        out: Dict[str, Any] = {}
        try:
            from core.prompt_registry import PromptRegistry
            out["prompt_rollback"] = PromptRegistry(self.db_path).rollback("rsi_heal_system")
        except Exception as e:
            out["prompt_rollback"] = f"napaka: {e}"
        try:
            from core.tuning import Tuning, DEFAULT_PARAMS
            t = Tuning(self.db_path)
            out["tuning_rollback"] = {name: t.rollback(name) for name in DEFAULT_PARAMS}
        except Exception as e:
            out["tuning_rollback"] = f"napaka: {e}"
        return out

    def check(self, before_id: int, auto_rollback: bool = True) -> Dict[str, Any]:
        """Primerja in (opcijsko) avtomatsko povrne ob regresiji."""
        result = self.compare(before_id)
        if result.get("regressed") and auto_rollback:
            result["rolled_back"] = self.rollback_improvements()
        return result

    # ------------------------------------------------------------------ #
    #  Pregled
    # ------------------------------------------------------------------ #
    def history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM meta_snapshots ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["metrics"] = json.loads(d["metrics"])
                out.append(d)
            return out

    def stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM meta_snapshots").fetchone()["n"]
        return {"snapshots": total, "current": self.metrics()}


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="meta_eval", description="Zanka 4 — meta-evalvacija samorazvoja.")
    p.add_argument("--metrics", action="store_true", help="trenutne metrike")
    p.add_argument("--snapshot", metavar="LABEL", nargs="?", const="", help="shrani baseline")
    p.add_argument("--check", type=int, metavar="SNAPSHOT_ID", help="primerjaj in povrni ob regresiji")
    p.add_argument("--history", action="store_true", help="zgodovina snapshot-ov")
    args = p.parse_args(argv)

    e = MetaEvaluator()
    if args.metrics:
        print(json.dumps(e.metrics(), ensure_ascii=False, indent=2))
    elif args.snapshot is not None:
        sid = e.snapshot(args.snapshot)
        print(f"snapshot {sid}")
    elif args.check:
        print(json.dumps(e.check(args.check), ensure_ascii=False, indent=2))
    elif args.history:
        for s in e.history():
            m = s["metrics"]
            print(f"#{s['id']} [{s['label'] or '-'}] success={m['success_rate']} llm={m['avg_llm_calls']}")
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
