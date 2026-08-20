"""core/fork.py — Faza 8 / Zanka 8: paralelno raziskovanje (fork).

Namesto ene poti sistem razišče N kandidatnih PRISTOPOV k istemu cilju, vsakega
oceni, in vrne najboljšega. To je "paralelni sprint": raziskovanje prostora
rešitev, ne slepo izvajanje ene poti.

Sestavi prejšnji zanki:
  - svetovni model (Zanka 7) da osnovno verjetnost uspeha (projektna/globalna),
  - critic (Zanka 6) adversarialno oceni KAKOVOST vsakega pristopa (severity).

Skupna ocena = osnovna verjetnost − kazen za tvegan pristop. Zmagovalec se
lahko izvede (explore_and_run) ali vrne klicatelju za nadaljnjo izbiro.

Uporaba:
  python core/fork.py --explore "zgradi API za avtentikacijo" --n 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ → koren repo
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Kazen za tvegan pristop (odšteje se od osnovne verjetnosti uspeha).
SEVERITY_PENALTY = {"low": 0.0, "medium": 0.1, "high": 0.25}


class Explorer:
    """Razišče N pristopov in vrne najboljšega (fork)."""

    def __init__(self, db_path: Path | str = Path(".rob_ai/memory.db")):
        if not Path(db_path).is_absolute():
            self.db_path = PROJECT_ROOT / db_path
        else:
            self.db_path = Path(db_path)

    # ------------------------------------------------------------------ #
    #  Generiranje + ocenjevanje pristopov
    # ------------------------------------------------------------------ #
    def propose_variants(self, goal: str, n: int = 3) -> List[str]:
        """LLM predlaga N različnih pristopov. Fallback: [cilj]."""
        if not self._llm_available():
            return [goal]
        system_prompt = (
            "Si raziskovalec rešitev. Za dani cilj predlagaj N RAZLIČNIH, smiselnih "
            "pristopov (strategij izvedbe). Vsak pristop naj bo kratek, samostojen opis, "
            "ki ga lahko izvede ena RSI gradnja."
        )
        prompt = f"Cilj: {goal}\n\nVrni STROGO JSON array: [\"pristop 1\", \"pristop 2\", ...]. Natančno {n} pristopov."
        try:
            from core.llm_client import DeepSeekLLMClient
            llm = DeepSeekLLMClient()
            raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        except Exception:
            return [goal]
        variants = self._parse_json_array(raw)
        variants = [str(v).strip() for v in variants if str(v).strip()]
        return variants[:n] if variants else [goal]

    def _critique(self, goal: str, variant: str) -> Dict[str, Any]:
        """Critic (Zanka 6) oceni tveganost pristopa."""
        from core.team import TeamCoordinator
        return TeamCoordinator().critique(goal, variant)

    def score(self, goal: str, variant: str, project: Optional[str] = None) -> Dict[str, Any]:
        """Oceni pristop: osnovna verjetnost (svetovni model) − kazen (critic)."""
        from core.world_model import WorldModel
        base = WorldModel(self.db_path).predict(variant, project)
        critique = self._critique(goal, variant)
        severity = critique.get("severity") if critique.get("severity") in SEVERITY_PENALTY else "low"
        score = max(0.05, min(0.95, base["success_prob"] - SEVERITY_PENALTY[severity]))
        return {
            "variant": variant,
            "success_prob": round(score, 3),
            "base_rate": base["success_prob"],
            "severity": severity,
            "objections": critique.get("objections", []),
        }

    def explore(self, goal: str, n: int = 3, project: Optional[str] = None) -> Dict[str, Any]:
        """Predlagaj N pristopov, oceni vsakega, vrni razvrščene + najboljšega."""
        variants = self.propose_variants(goal, n)
        scored = [self.score(goal, v, project) for v in variants]
        scored.sort(key=lambda s: s["success_prob"], reverse=True)
        return {
            "goal": goal,
            "variants": len(scored),
            "ranked": scored,
            "best": scored[0] if scored else None,
        }

    def explore_and_run(self, goal: str, n: int = 3, project: Optional[str] = None,
                        executor: Optional[Callable[[str], bool]] = None) -> Dict[str, Any]:
        """Razišči in izvedi najboljši pristop skozi executor."""
        result = self.explore(goal, n, project)
        best = result["best"]
        if best is None:
            return result
        if executor is None:
            from core.orchestrator import RobAIOrchestrator
            executor = lambda g: RobAIOrchestrator._phase(project or "demo", g, "podcilj")
        try:
            result["executed"] = bool(executor(best["variant"]))
        except Exception:
            result["executed"] = False
        return result

    # ------------------------------------------------------------------ #
    #  Pomožne
    # ------------------------------------------------------------------ #
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
    p = argparse.ArgumentParser(prog="fork", description="Zanka 8 — paralelno raziskovanje (fork).")
    p.add_argument("--explore", metavar="GOAL", help="razišči N pristopov in razvrsti")
    p.add_argument("--n", type=int, default=3, help="število pristopov")
    p.add_argument("--project", default=None, help="ciljni modul")
    args = p.parse_args(argv)

    if args.explore:
        res = Explorer().explore(args.explore, n=args.n, project=args.project)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
