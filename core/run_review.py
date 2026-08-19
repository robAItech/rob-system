"""core/run_review.py — Faza 4c / Zanka 2: post-run samoevalvacija odločitev.

QA verifičira KODO (pytest zelen/rdeč). Nihče pa ne evalvira ODLOČITEV — je bil
plan pravilen? Je ``spec_hint`` pomagal? Je blacklist deloval? Ta modul doda
post-run review: po vsakem RSI teku klasificira VZROK uspeha/neuspeha na nivoju
odločitve (ne testa) in zapiše lekcijo nazaj v spomin (Zanka 1).

To zapre učno zanko na PRAVI višini: namesto "pytest je padel" dobimo
"spec_hint je bil dvoumen, zato je LLM zgradil napačno arhitekturo".

Vpleten v ``loopx_bridge.execute_and_heal`` (po koncu zanke). Nikoli ne blokira
builda — vsaka napaka v recenziji je zgolj opozorilo.

Uporaba (ročni pregled):
  python core/run_review.py --recent          # zadnje recenzije
  python core/run_review.py --stats           # statistika recenzij
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo

# Samostojna skripta mora imeti repo koren na sys.path (enako kot run_swarm.py).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Možni vzroki uspeha/neuspeha na nivoju odločitve.
ROOT_CAUSES = (
    "correct",           # zelen — pravilna izvedba, nič za popraviti
    "spec_mismatch",     # direktiva/spec dvoumen ali napačno razumljen
    "llm_error",         # LLM generiral napačno/zlomljeno kodo
    "test_gap",          # testi prestrogi ali z napačno pričakovanim izidom
    "recurring_error",   # ista napaka se ponavlja (blacklist bi jo moral ujeti)
    "env_issue",         # okolje/odvisnost (ne koda)
    "unknown",           # ni mogoče določiti
)


class RunReviewer:
    """Po teku klasificira vzrok izida in zapiše lekcijo v spomin.

    Živi v isti bazi kot GBRAIN (``.rob_ai/memory.db``); lasti tabelo
    ``run_reviews``. Lekcijo (če je konkretna) vpiše tudi v ``semantic_memories``
    prek ``MemoryConsolidator.store``, da je takoj na voljo za priklic (Zanka 1).
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
                CREATE TABLE IF NOT EXISTS run_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL,
                    directive TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    root_cause TEXT NOT NULL,
                    lesson TEXT,
                    llm_calls INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    # ------------------------------------------------------------------ #
    #  Recenzija
    # ------------------------------------------------------------------ #
    def review(self, run: Dict[str, Any]) -> Dict[str, Any]:
        """Klasificira tek in zapiše recenzijo + lekcijo (če je konkretna).

        ``run`` pričakuje: project, directive, outcome ('green'|'failed'),
        traceback, llm_calls, attempts, spec_hint (vse opcijsko razen project).
        Vrne recenzijo (dict) — tudi če LLM odpove, vrne hevristiko.
        """
        outcome = run.get("outcome") if run.get("outcome") in ("green", "failed") else "failed"
        run = {**run, "outcome": outcome}

        if self._llm_available():
            try:
                result = self._review_via_llm(run)
            except Exception as e:
                print(f"[RUN-REVIEW] LLM recenzija ni uspela ({e}) — hevristika.", flush=True)
                result = self._review_heuristic(run)
        else:
            result = self._review_heuristic(run)

        root_cause = result["root_cause"] if result["root_cause"] in ROOT_CAUSES else "unknown"
        lesson = (result.get("lesson") or "").strip()
        if len(lesson) < 30:
            lesson = ""  # presplošna/prazna lekcija ni vredna zapisa

        self._insert_review(run, root_cause, lesson)

        # Zapri zanko: konkretno lekcijo takoj vpiši v semantični spomin (Zanka 1).
        if lesson:
            try:
                from core.memory_consolidation import MemoryConsolidator
                MemoryConsolidator(self.db_path).store(
                    theme=f"{run['project']}: {root_cause}",
                    content=lesson,
                    project="",
                    kind="pitfall" if outcome == "failed" else "principle",
                    confidence=0.5,
                )
            except Exception as e:
                print(f"[RUN-REVIEW] vpis lekcije ni uspel ({e})", flush=True)

        return {"project": run["project"], "outcome": outcome, "root_cause": root_cause, "lesson": lesson}

    def _review_via_llm(self, run: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = (
            "Si post-run recenzent avtonomnega inženirskega sistema. "
            "Klasificiraj VZROK uspeha/neuspeha teka na nivoju odločitve (ne testa) "
            "in izlušči eno kratko, specifično, ponovno uporabljivo lekcijo."
        )
        prompt = (
            f"Projekt: {run.get('project')}\n"
            f"Direktiva: {(run.get('directive') or '')[:500]}\n"
            f"Izid: {run.get('outcome')}\n"
            f"LLM klicev: {run.get('llm_calls', 0)} · poskusov: {run.get('attempts', 0)}\n"
            f"Spec hint: {(run.get('spec_hint') or '(brez)')[:300]}\n"
            f"Razlog (traceback): {(run.get('traceback') or '(brez)')[:800]}\n\n"
            "Vrni STROGO JSON objekt (nič drugega): "
            '{"root_cause": "<en od>", "lesson": "<kratka lekcija ali prazno ''>"}\n'
            f"root_cause ∈ {list(ROOT_CAUSES)}.\n"
            "lesson: če ni konkretne, ponovno uporabljive lekcije, vrni prazno."
        )
        from core.llm_client import DeepSeekLLMClient
        llm = DeepSeekLLMClient()
        raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        return self._parse_json_object(raw)

    def _review_heuristic(self, run: Dict[str, Any]) -> Dict[str, Any]:
        """Determinističen fallback brez LLM-a."""
        if run.get("outcome") == "green":
            return {"root_cause": "correct", "lesson": ""}
        tb = (run.get("traceback") or "")
        if "ista napaka" in tb:
            rc = "recurring_error"
        elif re.search(r"\w+(Error|Exception)", tb):
            rc = "llm_error"
        elif "test" in tb.lower() or "assert" in tb.lower():
            rc = "test_gap"
        else:
            rc = "unknown"
        return {"root_cause": rc, "lesson": f"V projektu {run.get('project')} se je pojavil vzorec '{rc}'."}

    @staticmethod
    def _parse_json_object(text: str) -> Dict[str, Any]:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            val = json.loads(text[start:end + 1])
            return val if isinstance(val, dict) else {}
        except Exception:
            return {}

    def _insert_review(self, run: Dict[str, Any], root_cause: str, lesson: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO run_reviews (project, directive, outcome, root_cause, lesson, llm_calls, attempts) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run.get("project", ""), run.get("directive", ""), run.get("outcome", ""),
                 root_cause, lesson, int(run.get("llm_calls", 0) or 0), int(run.get("attempts", 0) or 0)),
            )
            conn.commit()

    # ------------------------------------------------------------------ #
    #  Pregled
    # ------------------------------------------------------------------ #
    def recent(self, project: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            if project:
                rows = conn.execute(
                    "SELECT * FROM run_reviews WHERE project = ? ORDER BY id DESC LIMIT ?",
                    (project, limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM run_reviews ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM run_reviews").fetchone()["n"]
            by_cause = {r["root_cause"]: r["n"] for r in conn.execute(
                "SELECT root_cause, COUNT(*) AS n FROM run_reviews GROUP BY root_cause"
            ).fetchall()}
            by_outcome = {r["outcome"]: r["n"] for r in conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM run_reviews GROUP BY outcome"
            ).fetchall()}
        return {"reviews": total, "by_cause": by_cause, "by_outcome": by_outcome}

    @staticmethod
    def _llm_available() -> bool:
        try:
            from core.config import settings
            return settings.is_real_key_available()
        except Exception:
            return False


# ---------------------------------------------------------------------- #
#  CLI
# ---------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="run_review", description="Zanka 2 — post-run samoevalvacija.")
    p.add_argument("--recent", action="store_true", help="izpiši zadnje recenzije")
    p.add_argument("--project", default=None, help="omeji --recent na projekt")
    p.add_argument("--stats", action="store_true", help="statistika recenzij")
    args = p.parse_args(argv)

    r = RunReviewer()
    if args.recent:
        for row in r.recent(project=args.project):
            print(f"[{row['id']} · {row['outcome']:6} · {row['root_cause']:14}] {row['project']} — {row['lesson'] or '(brez lekcije)'}")
    elif args.stats:
        print(json.dumps(r.stats(), ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
