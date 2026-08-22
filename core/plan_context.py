"""core/plan_context.py — P2: determinističen izvleček naučenega za PLAN prompt.

Pred načrtovanjem (task_planner, team, run_autonomous) sistem dobi pretekle
lekcije + world-model napoved + aktivna operativna načela (P3) — "načrtuj z
izkušnjo, ne na slepo". Deterministično (fiksni vrstni red sekcij, cap preskoči
cele bloke), tolerantno (izjema → prazna sekcija), nikoli ne kliče LLM.

Markerja `[PLAN KONTEKST]`/`=== KONIEC KONTEKSTA ===` omogočata `strip_plan_context`
v `_detect_kind`, da prefiks ne spremeni klasifikacije vrste izdelka.
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

PLAN_CTX_HEADER = "[PLAN KONTEKST]"
PLAN_CTX_FOOTER = "=== KONIEC KONTEKSTA ==="
DEFAULT_MAX_CHARS = 2000

PRINCIPLES_PROMPT_NAME = "rsi_principles"


def _resolve_db(db_path) -> Path:
    p = Path(db_path)
    return PROJECT_ROOT / p if not p.is_absolute() else p


def _semantic_lessons(db: Path, project: str, goal: str) -> str:
    try:
        from core.memory_consolidation import MemoryConsolidator
        hits = MemoryConsolidator(db).recall(goal, project=project or None, limit=3)
        return "\n".join(
            f"- [{m.get('kind', '?')}] {m.get('theme', '')}: {str(m.get('content', ''))[:120]}"
            for m in hits
        )
    except Exception:
        return ""


def _recent_reviews(db: Path, project: str) -> str:
    try:
        from core.run_review import RunReviewer
        rows = RunReviewer(db).recent(project=project or None, limit=5)
        lines = []
        for r in rows:
            note = (r.get("what_worked") or r.get("what_failed") or r.get("lesson") or "")
            lines.append(f"- [{r.get('outcome', '?')}/{r.get('root_cause', '?')}] "
                         f"{r.get('project', '')}: {str(note)[:100]}")
        return "\n".join(lines)
    except Exception:
        return ""


def _world_prediction(db: Path, project: str, goal: str) -> str:
    try:
        from core.world_model import WorldModel
        p = WorldModel(db).predict(goal, project or None)
        return (f"uspeh={p.get('success_prob')} · prič.LLM={p.get('expected_llm_calls')} · "
                f"vzrok={p.get('likely_cause')} · pasti={p.get('pitfalls')} · base={p.get('base_rate')}")
    except Exception:
        return ""


def _active_principles(db: Path) -> str:
    try:
        from core.prompt_registry import PromptRegistry
        content = PromptRegistry(db).get_active(PRINCIPLES_PROMPT_NAME, "")
        if not content:
            return ""
        try:
            arr = json.loads(content)
            return "\n".join(
                f"- {p.get('principle')}" + (f" — {p.get('rationale')}" if p.get("rationale") else "")
                for p in arr if isinstance(p, dict) and p.get("principle")
            )
        except Exception:
            return content[:600]
    except Exception:
        return ""


def build_plan_context(db_path=Path(".rob_ai/memory.db"), project: str = "", goal: str = "",
                       max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """Determinističen izvleček naučenega za plan prompt. Cap preskoči cele bloke."""
    try:
        from core.config import settings
        if not settings.llm_plan_context:
            return ""
    except Exception:
        pass
    db = _resolve_db(db_path)
    sections: List[tuple] = [
        ("PREJŠNJE LEKCIJE (semantične)", _semantic_lessons(db, project, goal)),
        ("ZADNJI TEKI (task_lessons)", _recent_reviews(db, project)),
        ("NAPOVED SVETOVNEGA MODELA", _world_prediction(db, project, goal)),
        ("OPERATIVNA NAČELA (P3)", _active_principles(db)),
    ]
    out: List[str] = []
    for header, body in sections:
        if not body:
            continue
        block = f"## {header}\n{body}\n"
        if sum(len(s) for s in out) + len(block) > max_chars:
            continue
        out.append(block.rstrip())
    return "\n".join(out).strip()


def prepend_context(prompt: str, context: str) -> str:
    """Vstavi plan kontekst pred prompt (z markerjema za strip_plan_context)."""
    if not context:
        return prompt
    return f"{PLAN_CTX_HEADER}\n{context}\n{PLAN_CTX_FOOTER}\n\n{prompt}"


def strip_plan_context(text: str) -> str:
    """Odstrani [PLAN KONTEKST]...=== KONIEC KONTEKSTA === blok (za _detect_kind)."""
    if text.startswith(PLAN_CTX_HEADER) and PLAN_CTX_FOOTER in text:
        return text.split(PLAN_CTX_FOOTER, 1)[1].lstrip("\n")
    return text


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m core.plan_context",
                                description="P2 — determinističen plan kontekst (pretekle lekcije + napoved).")
    p.add_argument("--goal", default="", help="cilj naloge")
    p.add_argument("--project", default="", help="ciljni projekt")
    args = p.parse_args(argv)
    print(build_plan_context(project=args.project, goal=args.goal) or "(ni naučenega konteksta)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
