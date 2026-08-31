"""core/team.py — Faza 6 / Zanka 6: multi-agent adversarial koordinacija.

Do zdaj ima sistem ENEGA vodilnega agenta (GSTACK-Architect) + fiksen cevovod.
Zanka 6 doda DRUŽBO specialistov nad istim delom:

    planner (predlaga načrt) → critic (adversarialno izzove načrt)
        → builder (RSI izvede) → verifier (neodvisno potrdi)

Adversarialna zanka: critic oceni tveganje načrta; če je resno (severity=high),
planner načrt POPRAVI (revise), preden ga builder izvede. To odpravi
"en agent = ena slepa pega" — načrt je izzvan, preden se izvede, rezultat pa
neodvisno potrjen, preden se šteje za opravljenega.

Uporaba:
  python core/team.py --run "zgradi X" --project demo --dry-run
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

SEVERITIES = ("low", "medium", "high")


class TeamCoordinator:
    """Družba specialistov: planner → critic → builder → verifier.

    Vsaka vloga je LLM (DeepSeek) s hevrističnim fallbackom (brez ključa):
    planner → cilj, critic → low/brez ugovorov, verifier → ok. `executor` je
    vstavek (v produkciji RSI zanka, v testih mock).
    """

    # ------------------------------------------------------------------ #
    #  Vloge
    # ------------------------------------------------------------------ #
    def plan(self, goal: str, context: Optional[str] = None) -> str:
        """Planner predlaga kratek načrt izvedbe. Fallback: cilj."""
        if not self._llm_available():
            return goal
        system_prompt = "Si planner v avtonomnem podjetju. Predlagaj KRATEK, konkreten načrt izvedbe cilja."
        prompt = f"Cilj: {goal}\n\nNačrt (kratek, markdown):"
        if context:
            from core.plan_context import prepend_context
            prompt = prepend_context(prompt, context)
        try:
            from core.llm_client import DeepSeekLLMClient
            llm = DeepSeekLLMClient()
            raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
            return raw.strip() or goal
        except Exception:
            return goal

    def critique(self, goal: str, plan: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Critic adversarialno izzove načrt. Fallback: low, brez ugovorov."""
        if not self._llm_available():
            return {"severity": "low", "objections": []}
        system_prompt = "Si adversarial recenzent. Izzovi načrt: najdi tveganja, luknje, dvoumnosti."
        prompt = (
            f"Cilj: {goal}\n\nNačrt:\n{plan}\n\n"
            'Vrni STROGO JSON: {"severity": "low|medium|high", "objections": ["..."]}.'
        )
        if context:
            from core.plan_context import prepend_context
            prompt = prepend_context(prompt, context)
        try:
            from core.llm_client import DeepSeekLLMClient
            llm = DeepSeekLLMClient()
            raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        except Exception:
            return {"severity": "low", "objections": []}
        obj = self._parse_json_object(raw)
        severity = obj.get("severity") if obj.get("severity") in SEVERITIES else "low"
        objections = [str(o) for o in obj.get("objections", []) if str(o).strip()]
        return {"severity": severity, "objections": objections}

    def revise(self, goal: str, plan: str, objections: List[str], context: Optional[str] = None) -> str:
        """Planner popravi načrt glede na ugovore. Fallback: nespremenjen."""
        if not self._llm_available() or not objections:
            return plan
        system_prompt = "Si planner. Popravi načrt tako, da odpraviš naslednje ugovore."
        prompt = (
            f"Cilj: {goal}\n\nNačrt:\n{plan}\n\nUgovori:\n"
            + "\n".join(f"- {o}" for o in objections)
            + "\n\nPopravljen načrt:"
        )
        if context:
            from core.plan_context import prepend_context
            prompt = prepend_context(prompt, context)
        try:
            from core.llm_client import DeepSeekLLMClient
            llm = DeepSeekLLMClient()
            raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
            return raw.strip() or plan
        except Exception:
            return plan

    def _test_confidence(self, project: str) -> Dict[str, Any]:
        """Deterministična globina testov (Confidence Gate).

        Vsaka test funkcija mora imeti vsaj en `assert`; prazne test funkcije
        (brez assertion-a) so lažno pozitiven prehod. Vrne {score (0-1),
        total_tests, empty_tests}.
        """
        import ast
        d = Path(f"actions/{project}")
        total = empty = 0
        for tf in sorted(d.glob("test_*.py")):
            try:
                tree = ast.parse(tf.read_text(encoding="utf-8"))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                    total += 1
                    if not any(isinstance(n, ast.Assert) for n in ast.walk(node)):
                        empty += 1
        score = (total - empty) / total if total > 0 else 0.0
        return {"score": score, "total_tests": total, "empty_tests": empty}

    def _code_quality_score(self, project: str) -> Dict[str, Any]:
        """Deterministična ocena kakovosti kode (Evaluator-optimizer).

        Preveri prazne funkcije (samo ``pass``/docstring) in ``except:`` brez
        tipa (lovi vse). Vrne {score (0-1), empty_funcs, bare_excepts, issues}.
        """
        import ast
        d = Path(f"actions/{project}")
        total_funcs = empty_funcs = bare_excepts = 0
        issues: List[str] = []
        for f in sorted(d.glob("*.py")):
            if f.name.startswith("test_"):
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_funcs += 1
                    # Telo brez docstring-a/pass → prazna funkcija (stub).
                    real = [n for n in node.body
                            if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
                    if not real or all(isinstance(n, ast.Pass) for n in real):
                        empty_funcs += 1
                        issues.append(f"{f.name}:{node.name} je prazna (stub)")
                if isinstance(node, ast.ExceptHandler) and node.type is None:
                    bare_excepts += 1
                    issues.append(f"{f.name}: except: brez tipa (lovi vse)")
        if total_funcs == 0:
            return {"score": 1.0, "empty_funcs": 0, "bare_excepts": 0, "issues": []}
        penalty = (empty_funcs + bare_excepts) / total_funcs
        score = max(0.0, round(1.0 - penalty, 2))
        return {"score": score, "empty_funcs": empty_funcs, "bare_excepts": bare_excepts, "issues": issues[:5]}

    def verify(self, project: str, goal: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Verifier neodvisno potrdi, ali zgrajen modul izpolnjuje cilj.

        Dva deterministična gate-a pred LLM presojo:
        1. Confidence Gate — globina testov (prazni assert → lažno zeleno).
        2. Evaluator-optimizer — kakovost kode (prazne funkcije/bare except).
        """
        conf = self._test_confidence(project)
        if conf["total_tests"] > 0 and conf["score"] < 0.85:
            return {"ok": False, "reason": f"Zanesljivost testov {conf['score']:.2f} pod pragom 0.85 ({conf['empty_tests']}/{conf['total_tests']} testov brez assertion-a)."}
        qual = self._code_quality_score(project)
        if qual["score"] < 0.85:
            return {"ok": False, "reason": f"Kakovost kode {qual['score']:.2f} pod pragom 0.85: {qual['issues']}"}
        # REALITY CHECK — modul poženemo proti REALNIM sistem podatkom.
        # Ujame module, ki so "zeleni na svojih testih", ampak napačni v resnici
        # (npr. health_metrics z logiko state=='running'). Deterministično.
        try:
            from core.reality_check import run_reality_check
            rc = run_reality_check(project)
            if not rc["ok"]:
                return {"ok": False,
                        "reason": f"Reality check: {'; '.join(rc['issues'])}"}
        except Exception as e:
            return {"ok": False, "reason": f"Reality check napaka: {e}"}
        sources = self._read_sources(project)
        if not self._llm_available() or not sources:
            return {"ok": True, "reason": "hevristika (brez LLM ali brez vira)"}
        system_prompt = "Si verifikator. Neodvisno presodi, ali zgrajen modul izpolnjuje cilj."
        prompt = (
            f"Cilj: {goal}\n\nZgrajen modul (viri):\n{json.dumps(sources, ensure_ascii=False)[:4000]}\n\n"
            'Vrni STROGO JSON: {"ok": true|false, "reason": "..."}.'
        )
        if context:
            from core.plan_context import prepend_context
            prompt = prepend_context(prompt, context)
        try:
            from core.llm_client import DeepSeekLLMClient
            llm = DeepSeekLLMClient()
            raw = asyncio.run(llm.generate_completion(prompt=prompt, system_prompt=system_prompt, use_coder_model=False))
        except Exception:
            # FAIL-CLOSED: če verifikator (LLM) odpove, modul NE gre skozi brez
            # verifikacije. Retry zanka poskusi znova; trajna napaka → eskalacija.
            return {"ok": False, "reason": "verifikator ni dosegljiv (fail-closed)"}
        obj = self._parse_json_object(raw)
        return {"ok": bool(obj.get("ok", True)), "reason": str(obj.get("reason", ""))}

    # ------------------------------------------------------------------ #
    #  Cel cikel
    # ------------------------------------------------------------------ #
    def run(self, project: str, goal: str, executor: Optional[Callable[[str], bool]] = None,
            context: Optional[str] = None, max_attempts: Optional[int] = None) -> Dict[str, Any]:
        """Cel adversarial cikel: plan → critique → (revise) → build → verify,
        z RETRY ZANKO — če verify pade (reality check / kvaliteta), builder dobi
        povratno informacijo in poskusi znova (do `max_attempts`), nato eskalira.

        Vrne tudi `attempts` (koliko poskusov), `retried` (ali je bila retry) in
        `attempts_log` (vsi poskusi, za observabilnost).

        OMELJITEV: NE klici iz async konteksta — notranje funkcije (plan/critique/
        verify) uporabljajo `asyncio.run`, ki pade z RuntimeError, če je event loop
        že aktiven. Sync kontekst (daemon/run_swarm) je pravilen.

        `built=True` samo, če je modul zgrajen IN verificiran.
        """
        plan = self.plan(goal, context=context)
        critique = self.critique(goal, plan, context=context)
        revised = False
        if critique.get("severity") == "high":
            plan = self.revise(goal, plan, critique.get("objections", []), context=context)
            revised = True

        if executor is None:
            from core.orchestrator import RobAIOrchestrator
            executor = lambda g: RobAIOrchestrator._phase(project, g, "podcilj")
        if max_attempts is None:
            try:
                from core.config import settings
                max_attempts = getattr(settings, "team_max_attempts", 3)
            except Exception:
                max_attempts = 3
        max_attempts = max(1, int(max_attempts))

        last_verdict: Dict[str, Any] = {"ok": False, "reason": "ni bilo uspešnega poskusa"}
        attempts_log: List[Dict[str, Any]] = []
        attempt_goal = goal
        for attempt in range(1, max_attempts + 1):
            try:
                built = bool(executor(attempt_goal))
            except Exception:
                built = False
            last_verdict = self.verify(project, attempt_goal, context=context)
            attempts_log.append({
                "attempt": attempt,
                "built": built,
                "verdict": last_verdict,
            })
            if built and last_verdict.get("ok"):
                return {
                    "goal": goal,
                    "plan": plan[:500],
                    "severity": critique.get("severity"),
                    "objections": critique.get("objections", []),
                    "revised": revised,
                    "built": True,
                    "verdict": last_verdict,
                    "attempts": attempt,
                    "retried": attempt > 1,
                    "attempts_log": attempts_log,
                }
            # Ni uspelo → naslednji poskus z feedbackom (če imamo še poskuse).
            if attempt < max_attempts:
                reason = str(last_verdict.get("reason") or "preverjanje ni uspelo")[:400]
                attempt_goal = (
                    f"{goal}\n\nPREJŠNJI POSKUS NI USPEL: {reason}. "
                    f"Popravi zgrajeni modul (actions/{project}/), da opravi "
                    f"preverjanja (testi + kvaliteta + reality check)."
                )
        return {
            "goal": goal,
            "plan": plan[:500],
            "severity": critique.get("severity"),
            "objections": critique.get("objections", []),
            "revised": revised,
            "built": False,
            "verdict": last_verdict,
            "attempts": max_attempts,
            "retried": max_attempts > 1,
            "attempts_log": attempts_log,
        }

    # ------------------------------------------------------------------ #
    #  Pomožne
    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_sources(project: str) -> Dict[str, str]:
        d = Path(f"actions/{project}")
        out: Dict[str, str] = {}
        if d.exists():
            for p in d.glob("*.py"):
                try:
                    out[p.name] = p.read_text(encoding="utf-8")[:2000]
                except OSError:
                    pass
        return out

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
    p = argparse.ArgumentParser(prog="team", description="Zanka 6 — multi-agent adversarial koordinacija.")
    p.add_argument("--run", metavar="GOAL", help="cel adversarial cikel (plan → critique → build → verify)")
    p.add_argument("--project", default="demo", help="ciljni modul za --run")
    p.add_argument("--dry-run", action="store_true", help="pri --run: samo plan + critique, brez builda")
    args = p.parse_args(argv)

    tc = TeamCoordinator()
    if args.run:
        if args.dry_run:
            plan = tc.plan(args.run)
            critique = tc.critique(args.run, plan)
            print("PLAN:", plan[:500])
            print("CRITIQUE:", json.dumps(critique, ensure_ascii=False, indent=2))
        else:
            res = tc.run(args.project, args.run)
            print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
