"""core/task_planner.py — Faza 5 / Zanka 5: rekurzivna dekompozicija ciljev.

Danes ``RobAIOrchestrator.run_autonomous`` naredi le DVOfazno razdelitev
(spec + implement) po ključnih besedah. Zanka 5 doda PRAVO dekompozicijo:
LLM razbije kompleksen cilj na urejen seznam PODCILJEV (korakov), vsakega
izvede skozi RSI zanko, in združi rezultat.

To je prva SPOSOBNOSTNA zanka (po štirih samorazvojnih): dvigne zgornjo mejo
kompleksnosti — sistem lahko reši večkorakne naloge, ne le enopotezne.

Uporaba:
  python core/task_planner.py --decompose "zgradi spletno trgovino"
  python core/task_planner.py --execute "zgradi spletno trgovino" --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MAX_STEPS = 8  # zgornja meja števila podciljev


class TaskPlanner:
    """Razbije kompleksen cilj na podcilje in jih izvede skozi executor.

    ``executor`` je klic (podcilj → bool), v produkciji ``RobAIOrchestrator._phase``,
    v testih mock. Dekompozicija je LLM (DeepSeek); brez ključa → hevristika [cilj].
    """

    def decompose(self, goal: str, max_steps: int = MAX_STEPS, context: Optional[str] = None) -> List[str]:
        """LLM razbije cilj na urejene podcilje. Vrne seznam (fallback: [cilj]).

        `context` (P2): determinističen izvleček naučenega (pretekle lekcije +
        world-model napoved) — vstavi se pred prompt, da načrtovanje vidi izkušnje.
        """
        goal = (goal or "").strip()
        if not goal:
            return []
        if not self._llm_available():
            return self._decompose_heuristic(goal, max_steps)

        system_prompt = (
            "Si razčlenjevalnik nalog avtonomnega sistema. Kompleksen cilj razbij "
            "na urejen seznam KONKRETNIH, samostojnih, izvedljivih podciljev (korakov). "
            "Vsak korak mora biti dovolj ozek, da ga lahko izvede ena RSI gradnja."
        )
        prompt = (
            f"Cilj: {goal}\n\n"
            f"Vrni STROGO JSON array (nič drugega) oblike [\"korak 1\", \"korak 2\", ...]. "
            f"Največ {max_steps} korakov."
        )
        if context:
            from core.plan_context import prepend_context
            prompt = prepend_context(prompt, context)
        try:
            from core.llm_client import DeepSeekLLMClient
            llm = DeepSeekLLMClient()
            raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        except Exception as e:
            print(f"[PLAN] LLM dekompozicija ni uspela ({e}) — hevristika.", flush=True)
            return self._decompose_heuristic(goal, max_steps)

        steps = self._parse_json_array(raw)
        steps = [str(s).strip() for s in steps if str(s).strip()]
        return steps[:max_steps] if steps else self._decompose_heuristic(goal, max_steps)

    @staticmethod
    def _decompose_heuristic(goal: str, max_steps: int) -> List[str]:
        """Determinističen fallback: razdeli po ločilih ali vrne en sam korak."""
        for sep in ("; ", " nato ", " in nato ", " → "):
            if sep in goal:
                parts = [p.strip() for p in goal.split(sep) if p.strip()]
                if len(parts) > 1:
                    return parts[:max_steps]
        return [goal]

    def execute(self, goal: str, executor: Callable[[str], bool], max_steps: int = MAX_STEPS,
                context: Optional[str] = None) -> Dict[str, Any]:
        """Dekomponiraj cilj in izvedi vsak podcilj skozi executor.

        Vrne povzetek: število korakov, koliko uspešnih, in posamezni rezultati.
        Neustavlja se ob neuspehu posameznega koraka — izvede vse (best-effort).
        """
        steps = self.decompose(goal, max_steps, context=context)
        results: List[Dict[str, Any]] = []
        for step in steps:
            try:
                ok = bool(executor(step))
            except Exception as e:
                ok = False
                results.append({"step": step, "ok": False, "error": str(e)})
                continue
            results.append({"step": step, "ok": ok})

        completed = sum(1 for r in results if r["ok"])
        return {
            "goal": goal,
            "steps": len(steps),
            "completed": completed,
            "ok": completed == len(steps) and len(steps) > 0,
            "results": results,
        }

    @staticmethod
    def _parse_json_array(text: str) -> List[Any]:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            val = json.loads(text[start:end + 1])
            return val if isinstance(val, list) else []
        except Exception:
            return []

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
    p = argparse.ArgumentParser(prog="task_planner", description="Zanka 5 — dekompozicija ciljev.")
    p.add_argument("--decompose", metavar="GOAL", help="razbij cilj na podcilje (prikaži)")
    p.add_argument("--execute", metavar="GOAL", help="dekomponiraj in izvedi (dry-run prikaže korake)")
    p.add_argument("--dry-run", action="store_true", help="pri --execute: samo prikaži korake, ne izvajaj")
    args = p.parse_args(argv)

    tp = TaskPlanner()
    if args.decompose:
        steps = tp.decompose(args.decompose)
        for i, s in enumerate(steps, 1):
            print(f"{i}. {s}")
    elif args.execute:
        steps = tp.decompose(args.execute)
        if args.dry_run:
            for i, s in enumerate(steps, 1):
                print(f"{i}. {s}")
        else:
            # V produkciji bi bil executor RSI zanka; tu samo demonstracija.
            res = tp.execute(args.execute, executor=lambda s: True)
            print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
