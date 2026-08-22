"""core/strategy_reflect.py — P3: strateška samorefleksija (sistem razmišlja o tem,
kako razmišlja).

Iz zadnjih N `task_lessons` (run_reviews) LLM predlaga operativna načela
(verzionirano v `prompt_registry` pod imenom "rsi_principles"), ki jih LoopX
in plan-kontekst vbrizgata v prompte. Vzorec = `self_improve`: propose → guard →
evaluate (pytest) → promote/reject + `meta_eval` rollback ob regresiji.

Zagon:
  ./rob reflect --dry-run    # samo predlog (brez promocije)
  ./rob reflect --run        # predlagaj + promoviraj če testi zeleni
  ./rob reflect --current    # prikaži aktivna načela
  ./rob reflect --lessons    # prikaži zadnje task_lessons
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PRINCIPLES_PROMPT_NAME = "rsi_principles"
MAX_PRINCIPLES = 5
PRINCIPLE_MAX_CHARS = 200
RATIONALE_MAX_CHARS = 300
DEFAULT_TEST_TARGETS = ["tests/test_loopx_rsi.py", "tests/test_integration.py"]


class StrategyReflector:
    """Iz zadnjih task_lessons predlaga operativna načela (guard + pytest + rollback)."""

    def __init__(self, db_path: Path | str = Path(".rob_ai/memory.db")):
        if not Path(db_path).is_absolute():
            self.db_path = PROJECT_ROOT / db_path
        else:
            self.db_path = Path(db_path)

    # ------------------------------------------------------------------ #
    #  Lekcije
    # ------------------------------------------------------------------ #
    def gather_lessons(self, limit: int = 20) -> str:
        """Zadnjih N task_lessons (run_reviews) kot strnjen niz za LLM."""
        try:
            from core.run_review import RunReviewer
            rows = RunReviewer(self.db_path).recent(limit=limit)
        except Exception:
            return ""
        lines = []
        for r in rows:
            ww = (r.get("what_worked") or "").strip()[:120]
            wf = (r.get("what_failed") or "").strip()[:120]
            lesson = (r.get("lesson") or "").strip()[:120]
            parts = [f"[{r.get('outcome', '?')}·{r.get('root_cause', '?')}] {r.get('project', '')}"]
            goal = (r.get("goal") or r.get("directive") or "").strip()[:80]
            if goal:
                parts.append("cilj: " + goal)
            if ww:
                parts.append("delovalo: " + ww)
            if wf:
                parts.append("ni delovalo: " + wf)
            if lesson and lesson != ww and lesson != wf:
                parts.append("lekcija: " + lesson)
            lines.append("- " + " | ".join(parts))
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Predlog + guard
    # ------------------------------------------------------------------ #
    def propose_principles(self, lessons: str) -> Optional[List[Dict[str, Any]]]:
        """LLM → strict JSON array operativnih načel iz lekcij. Parse napaka → None."""
        if not lessons or not self._llm_available():
            return None
        system_prompt = (
            "Si strateški reflektor avtonomnega sistema. Iz nedavnih izidov nalog "
            "izlušči 1–5 KONKRETNIH, operativnih načel, ki bi izboljšala prihodnje "
            "izvedbe (ne splošnih floskul). Vsako načelo naj bo ukazovalno in "
            "uporabno v promptu agenta."
        )
        prompt = (
            f"Nedavne naloge (task_lessons):\n{lessons[:8000]}\n\n"
            "Vrni STROGO JSON array (nič drugega): "
            '[{"principle": "konkretno ukazovalno načelo (≤200 znakov)", '
            '"rationale": "zakaj (≤300 znakov)"}].\n'
            f"Največ {MAX_PRINCIPLES} načel. Če ni konkretnega izboljšanja, vrni []."
        )
        from core.llm_client import DeepSeekLLMClient
        llm = DeepSeekLLMClient()
        raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        arr = self._parse_json_array(raw)
        out = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            p = (str(item.get("principle", "")) or "").strip()
            r = (str(item.get("rationale", "")) or "").strip()
            if p:
                out.append({"principle": p[:PRINCIPLE_MAX_CHARS], "rationale": r[:RATIONALE_MAX_CHARS]})
        return out or None

    def guard_principles(self, principles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Strukturni guard + no-op guard (predlog ≠ aktivno — prepreči zanko)."""
        reasons = []
        if not isinstance(principles, list) or not (1 <= len(principles) <= MAX_PRINCIPLES):
            reasons.append(f"število načel izven meja (1..{MAX_PRINCIPLES})")
        seen = set()
        for it in principles:
            if not isinstance(it, dict):
                reasons.append("načelo ni objekt")
                continue
            p = (it.get("principle") or "").strip()
            if not p:
                reasons.append("načelo brez principa")
            if len(p) > PRINCIPLE_MAX_CHARS:
                reasons.append(f"princip > {PRINCIPLE_MAX_CHARS} znakov")
            low = p.lower()
            if low in seen:
                reasons.append("podvojena načela")
            seen.add(low)
        active = self.current_principles()
        if active and self._normalize(principles) == self._normalize(self._load_principles(active)):
            reasons.append("predlog identičen aktivnemu (no-op)")
        return {"ok": not reasons, "reasons": reasons}

    # ------------------------------------------------------------------ #
    #  Shramba (prompt_registry)
    # ------------------------------------------------------------------ #
    def store_principles(self, content: str) -> int:
        from core.prompt_registry import PromptRegistry
        return PromptRegistry(self.db_path).propose(PRINCIPLES_PROMPT_NAME, content, note="strategy-reflect (P3)")

    def current_principles(self) -> str:
        from core.prompt_registry import PromptRegistry
        return PromptRegistry(self.db_path).get_active(PRINCIPLES_PROMPT_NAME, "")

    @staticmethod
    def format_principles(content: str) -> str:
        """JSON → bralno berljiv seznam (za plan_context + injekcijo)."""
        try:
            arr = json.loads(content)
            return "\n".join(
                f"- {p.get('principle')}" + (f" — {p.get('rationale')}" if p.get("rationale") else "")
                for p in arr if isinstance(p, dict) and p.get("principle")
            )
        except Exception:
            return content

    @staticmethod
    def _normalize(principles) -> str:
        return json.dumps(principles, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def _load_principles(content: str) -> List[Dict[str, Any]]:
        try:
            arr = json.loads(content)
            return arr if isinstance(arr, list) else []
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    #  Cikel (propose → guard → store → pytest → promote/reject)
    # ------------------------------------------------------------------ #
    def evaluate(self, test_targets: Optional[List[str]] = None) -> bool:
        """Reuse: SelfImprover.evaluate (pytest podproces)."""
        from core.self_improve import SelfImprover
        return SelfImprover(self.db_path).evaluate(test_targets)

    def run_cycle(self, dry_run: bool = False, test_targets: Optional[List[str]] = None,
                  before_snapshot_id: Optional[int] = None) -> Dict[str, Any]:
        lessons = self.gather_lessons(20)
        principles = self.propose_principles(lessons)
        if principles is None:
            return {"proposed": False, "reason": "ni lekcij, ni ključa ali LLM ni predlagal"}
        guard = self.guard_principles(principles)
        if not guard["ok"]:
            return {"proposed": True, "promoted": False, "reason": f"guard: {guard['reasons']}"}
        content = json.dumps(principles, ensure_ascii=False)
        version_id = self.store_principles(content)
        if dry_run:
            return {"proposed": True, "version_id": version_id, "dry_run": True, "principles": principles}
        passed = self.evaluate(test_targets)
        self._mark(version_id, passed)
        if not passed:
            return {"proposed": True, "version_id": version_id, "promoted": False, "tests_passed": False}
        from core.prompt_registry import PromptRegistry
        PromptRegistry(self.db_path).promote(PRINCIPLES_PROMPT_NAME, version_id)
        result = {"proposed": True, "version_id": version_id, "promoted": True, "tests_passed": True}
        if before_snapshot_id:
            try:
                from core.meta_eval import MetaEvaluator
                cmp = MetaEvaluator(self.db_path).compare(before_snapshot_id)
                if cmp.get("regressed"):
                    PromptRegistry(self.db_path).rollback(PRINCIPLES_PROMPT_NAME)
                    result["rolled_back"] = True
            except Exception as e:
                result["meta_eval_error"] = str(e)
        return result

    def _mark(self, version_id: int, passed: bool) -> None:
        from core.prompt_registry import PromptRegistry
        PromptRegistry(self.db_path).mark(version_id, "proposed", tests_passed=1 if passed else 0)

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
def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m core.strategy_reflect",
                                description="P3 — strateška samorefleksija (operativna načela iz lekcij).")
    p.add_argument("--run", action="store_true", help="predlagaj + promoviraj če testi zeleni")
    p.add_argument("--dry-run", action="store_true", help="samo predlog, brez promocije")
    p.add_argument("--current", action="store_true", help="prikaži aktivna načela")
    p.add_argument("--lessons", action="store_true", help="prikaži zadnje task_lessons")
    p.add_argument("--snapshot", metavar="LABEL", default=None, help="meta snapshot pred spremembo")
    p.add_argument("--check", metavar="ID", default=None, help="preveri regresijo po snapshotu + rollback")
    args = p.parse_args(argv)

    r = StrategyReflector()
    if args.current:
        content = r.current_principles()
        print(r.format_principles(content) if content else "(ni aktivnih načel)")
        return 0
    if args.lessons:
        print(r.gather_lessons(20) or "(ni task_lessons)")
        return 0
    if args.check:
        from core.meta_eval import MetaEvaluator
        from core.prompt_registry import PromptRegistry
        result = MetaEvaluator(r.db_path).check(int(args.check))
        if result.get("regressed"):
            PromptRegistry(r.db_path).rollback(PRINCIPLES_PROMPT_NAME)
            result["principles_rolled_back"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.snapshot:
        from core.meta_eval import MetaEvaluator
        sid = MetaEvaluator(r.db_path).snapshot(args.snapshot)
        print(f"Snapshot {sid} shranjen.")
        return 0
    if args.run or args.dry_run:
        before = None
        if args.snapshot:
            from core.meta_eval import MetaEvaluator
            before = MetaEvaluator(r.db_path).snapshot(args.snapshot)
        res = r.run_cycle(dry_run=args.dry_run, before_snapshot_id=before)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
