"""core/learning_dashboard.py — P7: learning dashboard.

Prikaže, kaj se je sistem naučil: eval trend, sistemske metrike, aktivna
operativna načela (P3), dominantne prečne vzorce (P5) in zadnje per-task
lekcije. Samostojen, tolerantno (vsaka sekcija v try/except → "(ni podatkov)").

Uporaba:
  python -m core.learning_dashboard [--max-lessons N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

EVAL_HISTORY_DEFAULT = PROJECT_ROOT / ".rob_ai" / "eval_history.json"


def _metrics_block(db: Path) -> str:
    try:
        from core.meta_eval import MetaEvaluator
        m = MetaEvaluator(db).metrics()
        rate = f"{m['success_rate']:.0%}" if m.get("runs") else "n/a"
        lines = [f"  Tekov: {m.get('runs', 0)} · Zelenih: {m.get('green', 0)} · "
                 f"Neuspehov: {m.get('failed', 0)}",
                 f"  Uspešnost: {rate} · povpr. LLM klicev: {m.get('avg_llm_calls', 0)}"]
        if m.get("by_cause"):
            lines.append("  Po vzroku: " + ", ".join(f"{k}={v}" for k, v in m["by_cause"].items()))
        return "\n".join(lines)
    except Exception:
        return "  (ni podatkov)"


def _read_eval_history(path: Path) -> List[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _eval_trend_block(path: Path) -> str:
    hist = _read_eval_history(path)
    if not hist:
        return "  (ni eval zgodovine)"
    lines = []
    for e in hist[-6:]:
        lines.append(f"  {str(e.get('date', '?'))[:16]}  {float(e.get('rate', 0)) * 100:.0f}%")
    return "\n".join(lines)


def _principles_block(db: Path) -> str:
    try:
        from core.strategy_reflect import StrategyReflector
        r = StrategyReflector(db)
        content = r.current_principles()
        return r.format_principles(content) if content else "  (ni aktivnih načel)"
    except Exception:
        return "  (ni podatkov)"


def _patterns_block(db: Path, top: int = 3) -> str:
    try:
        from core.pattern_detect import PatternDetector
        patterns = PatternDetector(db).detect_cross_task_patterns()[:top]
        if not patterns:
            return "  (ni prečnih vzorcev)"
        return "\n".join(
            f"  [{p['cause']}] {p['total']}× v {p['projects']} projektih "
            f"({p['share']:.0%}) — {p['recommendation']}"
            for p in patterns
        )
    except Exception:
        return "  (ni podatkov)"


def _recent_lessons_block(db: Path, limit: int) -> str:
    try:
        from core.run_review import RunReviewer
        rows = RunReviewer(db).recent(limit=limit)
        if not rows:
            return "  (ni lekcij)"
        lines = []
        for r in rows:
            note = (r.get("what_worked") or r.get("what_failed") or r.get("lesson") or "")
            lines.append(f"  [{r.get('outcome', '?')}·{r.get('root_cause', '?')}] "
                         f"{r.get('project', '')}: {str(note)[:100]}")
        return "\n".join(lines)
    except Exception:
        return "  (ni podatkov)"


def render(max_lessons: int = 8,
           db_path: Path | str = Path(".rob_ai/memory.db"),
           eval_history_path: Path | str = EVAL_HISTORY_DEFAULT) -> str:
    """Learning dashboard kot ASCII niz. Tolerantno per sekcijo."""
    if not Path(db_path).is_absolute():
        db = PROJECT_ROOT / Path(db_path)
    else:
        db = Path(db_path)
    hist = Path(eval_history_path)
    return "\n".join([
        "SISTEMSKE METRIKE",
        _metrics_block(db),
        "",
        f"EVAL TREND (zadnjih 6)",
        _eval_trend_block(hist),
        "",
        "OPERATIVNA NAČELA (P3)",
        _principles_block(db),
        "",
        "DOMINANTNI VZORCI (P5)",
        _patterns_block(db),
        "",
        f"ZADNJE LEKCIJE",
        _recent_lessons_block(db, max_lessons),
    ])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m core.learning_dashboard",
                                description="P7 — learning dashboard.")
    p.add_argument("--max-lessons", type=int, default=8, help="število zadnjih lekcij")
    args = p.parse_args(argv)
    print(render(max_lessons=args.max_lessons))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
